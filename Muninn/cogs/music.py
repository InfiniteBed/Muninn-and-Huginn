import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import asyncio
import os
import sqlite3
import random
from collections import deque
import time
import re
import logging
import traceback
import aiohttp
import json
from typing import Optional, Dict, List, Any

try:
    from plexapi.server import PlexServer
    from plexapi.exceptions import PlexApiException
except Exception:  # pragma: no cover - fallback when plexapi isn't installed yet
    PlexServer = None
    PlexApiException = Exception  # type: ignore

def _import_load_global_config():
    # Try multiple import strategies so this cog can be loaded whether the
    # package is imported as `Muninn` (package-absolute) or as a top-level
    # `cogs` module. Falls back to loading the configuration.py file by path.
    try:
        from Muninn.configuration import load_global_config
        return load_global_config
    except Exception:
        pass
    try:
        # Try top-level import if the project root is on sys.path
        from configuration import load_global_config
        return load_global_config
    except Exception:
        pass
    try:
        # Try relative import when package context is different
        from ..configuration import load_global_config
        return load_global_config
    except Exception:
        pass

    # Last resort: import by file path relative to this file
    import importlib.util, os
    config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'configuration.py'))
    if os.path.exists(config_path):
        spec = importlib.util.spec_from_file_location('muninn_configuration', config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore
        return getattr(module, 'load_global_config')

    raise ImportError('Could not import load_global_config from Muninn.configuration or configuration.py')


load_global_config = _import_load_global_config()

# Set up logging
logger = logging.getLogger('music_bot')
logger.setLevel(logging.DEBUG)

# Real database class for music rating and caching system
class MusicEloDatabase:
    """Real database class for music rating and caching system"""
    def __init__(self, db_path='discord.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Songs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                artist TEXT,
                duration INTEGER,
                thumbnail_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Song ratings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS song_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (song_id) REFERENCES songs(id),
                UNIQUE(song_id, user_id, guild_id)
            )
        """)
        
        # Song play history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS song_plays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (song_id) REFERENCES songs(id)
            )
        """)
        
        # Cached songs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cached_songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                cache_reason TEXT NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                FOREIGN KEY (song_id) REFERENCES songs(id),
                UNIQUE(song_id, guild_id)
            )
        """)
        
        # Guild rating settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guild_rating_settings (
                guild_id INTEGER PRIMARY KEY,
                enable_reaction_rating BOOLEAN DEFAULT 1,
                show_ratings_in_now_playing BOOLEAN DEFAULT 1,
                min_ratings_to_show INTEGER DEFAULT 1
            )
        """)
        
        # Playlists table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                public BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, guild_id, name)
            )
        """)
        
        # Playlist songs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                song_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id),
                FOREIGN KEY (song_id) REFERENCES songs(id),
                UNIQUE(playlist_id, song_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_guild_rating_settings(self, guild_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT enable_reaction_rating, show_ratings_in_now_playing, min_ratings_to_show
            FROM guild_rating_settings WHERE guild_id = ?
        """, (guild_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'enable_reaction_rating': bool(result[0]),
                'show_ratings_in_now_playing': bool(result[1]),
                'min_ratings_to_show': result[2]
            }
        else:
            # Return defaults
            return {
                'enable_reaction_rating': True,
                'show_ratings_in_now_playing': True,
                'min_ratings_to_show': 1
            }
    
    def get_song_by_url(self, url):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM songs WHERE url = ?", (url,))
        result = cursor.fetchone()
        conn.close()
        
        return result
    
    def add_song(self, url, title, artist=None, duration=None, thumbnail_url=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO songs (url, title, artist, duration, thumbnail_url)
                VALUES (?, ?, ?, ?, ?)
            """, (url, title, artist, duration, thumbnail_url))
            
            song_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return song_id
        except sqlite3.IntegrityError:
            # Song already exists
            conn.close()
            existing_song = self.get_song_by_url(url)
            return existing_song[0] if existing_song else None
    
    def add_song_play(self, song_id, guild_id, user_id):
        """Record a song play"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO song_plays (song_id, guild_id, user_id)
            VALUES (?, ?, ?)
        """, (song_id, guild_id, user_id))
        
        conn.commit()
        conn.close()
    
    def add_song_rating(self, song_id, user_id, guild_id, rating):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO song_ratings (song_id, user_id, guild_id, rating)
                VALUES (?, ?, ?, ?)
            """, (song_id, user_id, guild_id, rating))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.close()
            logger.error(f"Error adding song rating: {e}")
            return False
    
    def get_song_rating_stats(self, song_id, guild_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT AVG(rating), COUNT(*), 
                   SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END)
            FROM song_ratings 
            WHERE song_id = ? AND guild_id = ?
        """, (song_id, guild_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[1] > 0:
            return {
                'avg_rating': float(result[0]),
                'total_ratings': result[1],
                'rating_distribution': {
                    '1': result[2],
                    '2': result[3],
                    '3': result[4],
                    '4': result[5],
                    '5': result[6]
                }
            }
        else:
            return {
                'avg_rating': 0.0,
                'total_ratings': 0,
                'rating_distribution': {}
            }
    
    def cleanup_expired_sessions(self):
        # This can be used for any cleanup tasks
        pass
    
    def get_user_ratings(self, user_id, guild_id, limit=10, offset=0):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.title, s.artist, sr.rating, sr.created_at
            FROM song_ratings sr
            JOIN songs s ON sr.song_id = s.id
            WHERE sr.user_id = ? AND sr.guild_id = ?
            ORDER BY sr.created_at DESC
            LIMIT ? OFFSET ?
        """, (user_id, guild_id, limit, offset))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_user_rating_count(self, user_id, guild_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM song_ratings 
            WHERE user_id = ? AND guild_id = ?
        """, (user_id, guild_id))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
    
    def get_top_rated_songs(self, guild_id, timeframe='all', limit=10):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timeframe_clause = ""
        if timeframe == 'day':
            timeframe_clause = "AND sr.created_at >= datetime('now', '-1 day')"
        elif timeframe == 'week':
            timeframe_clause = "AND sr.created_at >= datetime('now', '-7 days')"
        elif timeframe == 'month':
            timeframe_clause = "AND sr.created_at >= datetime('now', '-30 days')"
        
        cursor.execute(f"""
            SELECT s.title, s.artist, AVG(sr.rating) as avg_rating, COUNT(sr.rating) as rating_count
            FROM song_ratings sr
            JOIN songs s ON sr.song_id = s.id
            WHERE sr.guild_id = ? {timeframe_clause}
            GROUP BY s.id
            HAVING COUNT(sr.rating) >= 2
            ORDER BY avg_rating DESC, rating_count DESC
            LIMIT ?
        """, (guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_recent_ratings(self, song_id, guild_id, limit=5):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT sr.rating, sr.created_at, sr.user_id
            FROM song_ratings sr
            WHERE sr.song_id = ? AND sr.guild_id = ?
            ORDER BY sr.created_at DESC
            LIMIT ?
        """, (song_id, guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_user_recommendations(self, user_id, guild_id, limit=5):
        # Simple recommendation based on similar users' ratings
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.title, s.artist, AVG(sr.rating) as avg_rating
            FROM song_ratings sr
            JOIN songs s ON sr.song_id = s.id
            WHERE sr.guild_id = ? AND sr.song_id NOT IN (
                SELECT song_id FROM song_ratings WHERE user_id = ? AND guild_id = ?
            )
            GROUP BY s.id
            HAVING avg_rating >= 4.0
            ORDER BY avg_rating DESC
            LIMIT ?
        """, (guild_id, user_id, guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_top_rated_songs_as_playlist(self, guild_id, limit=50):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.url, s.title, s.artist, AVG(sr.rating) as avg_rating
            FROM song_ratings sr
            JOIN songs s ON sr.song_id = s.id
            WHERE sr.guild_id = ?
            GROUP BY s.id
            HAVING avg_rating >= 3.5
            ORDER BY avg_rating DESC
            LIMIT ?
        """, (guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def update_guild_rating_settings(self, guild_id, **settings):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO guild_rating_settings 
            (guild_id, enable_reaction_rating, show_ratings_in_now_playing, min_ratings_to_show)
            VALUES (?, ?, ?, ?)
        """, (
            guild_id,
            settings.get('enable_reaction_rating', True),
            settings.get('show_ratings_in_now_playing', True),
            settings.get('min_ratings_to_show', 1)
        ))
        
        conn.commit()
        conn.close()
        
        return True
    
    def create_playlist(self, user_id, guild_id, name, description=None, public=False):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO playlists (user_id, guild_id, name, description, public)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, guild_id, name, description, public))
            
            playlist_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return playlist_id
        except sqlite3.IntegrityError:
            conn.close()
            return None
    
    def get_user_playlists(self, user_id, guild_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, name, description, public, created_at
            FROM playlists
            WHERE user_id = ? AND guild_id = ?
            ORDER BY created_at DESC
        """, (user_id, guild_id))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_playlist_by_name(self, user_id, guild_id, name):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM playlists
            WHERE user_id = ? AND guild_id = ? AND name = ?
        """, (user_id, guild_id, name))
        
        result = cursor.fetchone()
        conn.close()
        
        return result
    
    def get_playlist_songs(self, playlist_id, limit=50):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.url, s.title, s.artist, ps.added_at
            FROM playlist_songs ps
            JOIN songs s ON ps.song_id = s.id
            WHERE ps.playlist_id = ?
            ORDER BY ps.added_at ASC
            LIMIT ?
        """, (playlist_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def search_songs_for_playlist(self, guild_id, search_term, limit=5):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT s.id, s.title, s.artist, s.url
            FROM songs s
            JOIN song_plays sp ON s.id = sp.song_id
            WHERE sp.guild_id = ? AND (s.title LIKE ? OR s.artist LIKE ?)
            ORDER BY s.title ASC
            LIMIT ?
        """, (guild_id, f"%{search_term}%", f"%{search_term}%", limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def add_song_to_playlist(self, playlist_id, song_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO playlist_songs (playlist_id, song_id)
                VALUES (?, ?)
            """, (playlist_id, song_id))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def remove_song_from_playlist(self, playlist_id, song_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM playlist_songs
            WHERE playlist_id = ? AND song_id = ?
        """, (playlist_id, song_id))
        
        conn.commit()
        conn.close()
        
        return cursor.rowcount > 0
    
    def delete_playlist(self, playlist_id, user_id, guild_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # First delete all songs from the playlist
        cursor.execute("DELETE FROM playlist_songs WHERE playlist_id = ?", (playlist_id,))
        
        # Then delete the playlist itself
        cursor.execute("""
            DELETE FROM playlists
            WHERE id = ? AND user_id = ? AND guild_id = ?
        """, (playlist_id, user_id, guild_id))
        
        conn.commit()
        conn.close()
        
        return cursor.rowcount > 0
    
    def cache_song(self, song_id, guild_id, reason, file_path=None, file_size=0):
        """Cache a song for quick access"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO cached_songs (song_id, guild_id, cache_reason, file_path, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (song_id, guild_id, reason, file_path, file_size))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.close()
            logger.error(f"Error caching song: {e}")
            return False
    
    def get_cached_songs(self, guild_id, limit=50):
        """Get all cached songs for a guild"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.title, s.artist, s.url, cs.cache_reason, cs.cached_at, cs.file_path, cs.file_size
            FROM cached_songs cs
            JOIN songs s ON cs.song_id = s.id
            WHERE cs.guild_id = ?
            ORDER BY cs.cached_at DESC
            LIMIT ?
        """, (guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_cached_file_path(self, url, guild_id):
        """Get cached file path for a song if it exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cs.file_path FROM cached_songs cs
            JOIN songs s ON cs.song_id = s.id
            WHERE s.url = ? AND cs.guild_id = ? AND cs.file_path IS NOT NULL
        """, (url, guild_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] and os.path.exists(result[0]):
            return result[0]
        return None
    
    def cleanup_invalid_cache_entries(self):
        """Remove cache entries for files that no longer exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, file_path FROM cached_songs WHERE file_path IS NOT NULL")
        entries = cursor.fetchall()
        
        removed_count = 0
        for entry_id, file_path in entries:
            if not os.path.exists(file_path):
                cursor.execute("DELETE FROM cached_songs WHERE id = ?", (entry_id,))
                removed_count += 1
        
        conn.commit()
        conn.close()
        
        return removed_count
    
    def update_song_cache(self, guild_id):
        """Update the cache with recently played songs and highly rated songs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear old cache
        cursor.execute("DELETE FROM cached_songs WHERE guild_id = ?", (guild_id,))
        
        # Cache songs played in the last month
        cursor.execute("""
            INSERT INTO cached_songs (song_id, guild_id, cache_reason)
            SELECT DISTINCT sp.song_id, sp.guild_id, 'recent_play'
            FROM song_plays sp
            WHERE sp.guild_id = ? AND sp.played_at >= datetime('now', '-30 days')
        """, (guild_id,))
        
        # Cache highly rated songs (rating > 2.5)
        cursor.execute("""
            INSERT OR IGNORE INTO cached_songs (song_id, guild_id, cache_reason)
            SELECT sr.song_id, sr.guild_id, 'high_rating'
            FROM song_ratings sr
            WHERE sr.guild_id = ? AND sr.song_id IN (
                SELECT song_id
                FROM song_ratings
                WHERE guild_id = ?
                GROUP BY song_id
                HAVING AVG(rating) > 2.5
            )
        """, (guild_id, guild_id))
        
        conn.commit()
        conn.close()
    
    def cleanup_old_data(self):
        """Clean up old data - called by midnight task"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Remove song plays older than 6 months
        cursor.execute("""
            DELETE FROM song_plays 
            WHERE played_at < datetime('now', '-6 months')
        """)
        
        # Remove cached songs that are no longer relevant
        cursor.execute("""
            DELETE FROM cached_songs 
            WHERE cached_at < datetime('now', '-1 day')
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("Cleaned up old music data")

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

# YT-DLP options for audio extraction
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Allow playlists
    'playlistend': 50,    # Limit to first 50 songs for performance
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractaudio': True,
    'audioformat': 'mp3',
    'audioquality': '192',
}

# FFmpeg options for streaming
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

_FFMPEG_EXECUTABLE_CACHE: Optional[str] = None


def get_ffmpeg_executable() -> str:
    global _FFMPEG_EXECUTABLE_CACHE
    if _FFMPEG_EXECUTABLE_CACHE:
        return _FFMPEG_EXECUTABLE_CACHE

    possible_paths = [
        './ffmpeg',
        './bin/ffmpeg',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'ffmpeg',
    ]

    for path in possible_paths:
        if path == 'ffmpeg':
            _FFMPEG_EXECUTABLE_CACHE = path
            return path
        if os.path.exists(path):
            _FFMPEG_EXECUTABLE_CACHE = path
            return path

    _FFMPEG_EXECUTABLE_CACHE = 'ffmpeg'
    return _FFMPEG_EXECUTABLE_CACHE

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')
        self.webpage_url = data.get('webpage_url')
        self.provider = data.get('provider', 'youtube')
        self.downloaded_file = None  # Will be set if file was downloaded
        self.original = source  # Add reference to original source for Discord.py compatibility
    
    def get_thumbnail_url(self):
        """Safely get thumbnail URL, returning None if not available"""
        return getattr(self, 'thumbnail', None)

    def cleanup(self):
        """Clean up downloaded file if it exists"""
        if self.downloaded_file and os.path.exists(self.downloaded_file):
            try:
                os.remove(self.downloaded_file)
                logger.debug(f"Cleaned up downloaded file: {self.downloaded_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up file {self.downloaded_file}: {e}")

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop=None, download=False, extract_playlist=False, force_cache=False):
        loop = loop or asyncio.get_event_loop()
        logger.info(f"Creating audio source for search: {search}")
        
        # Check if it's a URL or search query
        original_search = search
        is_playlist = False
        
        # Check if this looks like a playlist URL
        if 'playlist' in search.lower() or 'list=' in search:
            is_playlist = True
            extract_playlist = True
        
        if not re.match(r'^https?://', search) and not extract_playlist:
            search = f"ytsearch:{search}"
            logger.debug(f"Modified search query to: {search}")
        
        # First check if we have this song cached (only for single songs, not playlists)
        cached_file_path = None
        if not extract_playlist and hasattr(ctx, 'guild') and ctx.guild:
            try:
                db = MusicEloDatabase()
                # For URLs, check cache directly; for searches, we need to extract info first
                if re.match(r'^https?://', original_search):
                    cached_file_path = db.get_cached_file_path(original_search, ctx.guild.id)
                    if cached_file_path:
                        logger.info(f"Found cached file for {original_search}: {cached_file_path}")
                        # Get song metadata from database
                        song_row = db.get_song_by_url(original_search)
                        if song_row:
                            # Reconstruct data from database
                            fake_data = {
                                'url': cached_file_path,
                                'title': song_row[2],  # title
                                'duration': song_row[4],  # duration
                                'thumbnail': song_row[5],  # thumbnail_url
                                'uploader': song_row[3],  # artist
                                'webpage_url': song_row[1],  # url
                            }
                            
                            # Create FFmpeg source from cached file
                            ffmpeg_source = discord.FFmpegPCMAudio(
                                cached_file_path,
                                options='-vn'
                            )
                            
                            ytdl_source = cls(ffmpeg_source, data=fake_data)
                            ytdl_source.downloaded_file = cached_file_path
                            logger.info(f"Successfully created source from cached file: {song_row[2]}")
                            return ytdl_source
            except Exception as e:
                logger.warning(f"Error checking cache: {e}")
                # Continue with normal processing
        
        # Configure yt-dlp with options for caching
        cache_dir = 'audio_cache'
        os.makedirs(cache_dir, exist_ok=True)
        
        ytdl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{cache_dir}/%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': not extract_playlist,  # Allow playlists only when requested
            'quiet': True,
            'no_warnings': True,
            'extractaudio': True,
            'audioformat': 'mp3',
            'audioquality': '192',
            'default_search': 'auto',
        }
        
        if extract_playlist:
            ytdl_opts['playlistend'] = 50  # Limit playlists to 50 songs
        
        ytdl = yt_dlp.YoutubeDL(ytdl_opts)
        
        # Create downloads directory if it doesn't exist
        os.makedirs('downloads', exist_ok=True)
        
        try:
            # Extract info in a separate function (not lambda)
            async def extract_video_info():
                try:
                    logger.debug("Starting yt-dlp extraction")
                    # Run in executor to avoid blocking
                    def run_extraction():
                        try:
                            logger.debug("Inside run_extraction function")
                            # Extract info without downloading first
                            info = ytdl.extract_info(search, download=False)
                            logger.debug(f"yt-dlp extract_info completed successfully")
                            
                            # If this is a playlist and we want the full playlist, return it
                            if extract_playlist and 'entries' in info:
                                logger.debug(f"Extracted playlist with {len(info['entries'])} entries")
                                return info
                            
                            # For single videos, get the first entry if it's a search result
                            if 'entries' in info:
                                if not info['entries']:
                                    raise Exception("No search results found")
                                video_info = info['entries'][0]
                            else:
                                video_info = info
                            
                            # Try to get direct URL first
                            direct_url = video_info.get('url')
                            if direct_url and direct_url.startswith('http') and not force_cache:
                                logger.debug("Got direct stream URL, no download needed")
                                return {'single_video': video_info}
                            else:
                                logger.debug("No direct URL available or caching forced, downloading file")
                                # Download the file if no direct URL or caching is forced
                                ytdl_opts_download = ytdl_opts.copy()
                                ytdl_opts_download['noplaylist'] = True  # Never download full playlists
                                ytdl_download = yt_dlp.YoutubeDL(ytdl_opts_download)
                                downloaded_info = ytdl_download.extract_info(video_info.get('webpage_url', search), download=True)
                                logger.debug("yt-dlp download completed successfully")
                                return {'single_video': downloaded_info}
                                
                        except Exception as inner_e:
                            logger.error(f"Error inside run_extraction: {type(inner_e).__name__}: {inner_e}")
                            # Dump full stack trace to logs
                            import traceback
                            logger.error("FULL STACK TRACE FOR run_extraction ERROR:")
                            logger.error(traceback.format_exc())
                            raise
                    
                    logger.debug("About to call run_in_executor")
                    result = await loop.run_in_executor(None, run_extraction)
                    logger.debug(f"run_in_executor completed successfully")
                    return result
                except Exception as e:
                    logger.error(f"yt-dlp extraction failed: {type(e).__name__}: {e}", exc_info=True)
                    raise
            
            data = await extract_video_info()
            
            # If this is playlist data, return the entries as a list
            if extract_playlist and 'entries' in data:
                logger.debug(f"Processing playlist with {len(data['entries'])} entries")
                # Return the individual entries for processing
                return data['entries']
            
            # Handle single video
            if 'single_video' in data:
                data = data['single_video']
            elif 'entries' in data:
                # Take the first item from a playlist/search
                if not data['entries']:
                    logger.warning(f"No entries found for search: {original_search}")
                    raise commands.CommandError("No results found for your search query.")
                data = data['entries'][0]
                logger.debug(f"Using first entry: {data.get('title', 'Unknown')}")
            
            if not data:
                logger.warning(f"No data returned for search: {original_search}")
                raise commands.CommandError("No results found for your search query.")
            
            # Get the audio source (URL or file path)
            audio_source = data.get('url')
            downloaded_file = None
            
            # Check if this is a file path (downloaded) or URL (streaming)
            if audio_source and not audio_source.startswith('http'):
                # This is a downloaded file path
                downloaded_file = audio_source
                logger.info(f"Using downloaded file: {downloaded_file}")
            elif not audio_source:
                # Try to get the downloaded filename
                downloaded_file = ytdl.prepare_filename(data)
                if os.path.exists(downloaded_file):
                    audio_source = downloaded_file
                    logger.info(f"Using prepared filename: {downloaded_file}")
                else:
                    logger.error(f"No audio source found for: {original_search}")
                    raise commands.CommandError("❌ Could not find audio stream or file for this video")
            else:
                logger.info(f"Using stream URL: {data.get('title', 'Unknown')} - URL length: {len(audio_source)}")
            
            # Create FFmpeg audio source with explicit options
            try:
                logger.debug(f"Creating FFmpeg audio source from: {'file' if downloaded_file else 'stream'}")
                ffmpeg_executable = get_ffmpeg_executable()

                if downloaded_file:
                    # For downloaded files, use simpler options
                    ffmpeg_source = discord.FFmpegPCMAudio(
                        audio_source,
                        executable=ffmpeg_executable,
                        options='-vn'
                    )
                else:
                    # For streaming, use reconnect options
                    ffmpeg_source = discord.FFmpegPCMAudio(
                        audio_source,
                        executable=ffmpeg_executable,
                        before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                        options='-vn'
                    )
                
                logger.info(f"Successfully created audio source for: {data.get('title', 'Unknown')}")
                
                # Store the downloaded file path for cleanup later
                ytdl_source = cls(ffmpeg_source, data=data)
                ytdl_source.downloaded_file = downloaded_file
                
                # Cache the file if it was downloaded and we have guild context
                if downloaded_file and hasattr(ctx, 'guild') and ctx.guild:
                    try:
                        db = MusicEloDatabase()
                        # Add song to database if not present
                        song_row = db.get_song_by_url(data.get('webpage_url'))
                        if not song_row:
                            song_id = db.add_song(
                                url=data.get('webpage_url'),
                                title=data.get('title'),
                                artist=data.get('uploader'),
                                duration=data.get('duration'),
                                thumbnail_url=data.get('thumbnail')
                            )
                        else:
                            song_id = song_row[0]
                        
                        if song_id:
                            file_size = os.path.getsize(downloaded_file) if os.path.exists(downloaded_file) else 0
                            db.cache_song(song_id, ctx.guild.id, 'downloaded', downloaded_file, file_size)
                            logger.info(f"Cached audio file: {data.get('title')} ({file_size} bytes)")
                    except Exception as e:
                        logger.warning(f"Failed to cache song in database: {e}")
                
                return ytdl_source
                
            except Exception as ffmpeg_error:
                logger.error(f"FFmpeg audio source creation failed: {ffmpeg_error}", exc_info=True)
                # Pass through the full error details
                raise commands.CommandError(f"❌ Failed to create audio source: {type(ffmpeg_error).__name__}: {str(ffmpeg_error)}")
            
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error for '{original_search}': {e}")
            if "Video unavailable" in str(e):
                raise commands.CommandError("❌ This video is unavailable (may be private, deleted, or region-locked)")
            elif "Sign in to confirm your age" in str(e):
                raise commands.CommandError("❌ This video is age-restricted and cannot be played")
            else:
                raise commands.CommandError(f"❌ Download error: {type(e).__name__}: {str(e)}")
        except commands.CommandError:
            # Re-raise command errors as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error in create_source for '{original_search}': {e}", exc_info=True)
            # Pass through full error details including type and traceback info
            import traceback
            tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error(f"Full traceback: {tb_str}")
            raise commands.CommandError(f"❌ Error extracting audio: {type(e).__name__}: {str(e)}")


class PlexAudioSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: Dict[str, Any], volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('stream_url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('artist')
        self.album = data.get('album')
        self.webpage_url = data.get('webpage_url')
        self.provider = 'plex'
        self.downloaded_file = None
        self.original = source

    def cleanup(self):
        """Plex streams are remote; nothing to clean up."""
        return


class PlexMusicProvider:
    def __init__(self, *, base_url: str, token: str, allow_transcode: bool = True, timeout: int = 10):
        if not PlexServer:
            raise RuntimeError("plexapi is not installed; install plexapi to enable Plex integration")

        self.base_url = base_url.rstrip('/')
        self.token = token
        self.allow_transcode = allow_transcode
        self.timeout = timeout
        self._client: Any = None
        self._library_cache: Dict[str, Any] = {}
        self._signature = (self.base_url, self.token, self.allow_transcode, self.timeout)

    @property
    def signature(self) -> tuple[str, str, bool, int]:
        return self._signature

    def _connect(self):
        if not self._client:
            self._client = PlexServer(self.base_url, self.token, timeout=self.timeout)
        return self._client

    def _get_library(self, library_name: str):
        library_key = library_name or '__default__'
        if library_key in self._library_cache:
            return self._library_cache[library_key]

        server = self._connect()
        library = server.library.section(library_name)
        self._library_cache[library_key] = library
        return library

    async def resolve_track(self, query: str, library_name: str) -> Optional[Dict[str, Any]]:
        def _resolve() -> Optional[Dict[str, Any]]:
            library = self._get_library(library_name)
            results = library.searchTracks(query, maxresults=5)
            if not results:
                return None

            track = results[0]
            if self.allow_transcode:
                stream_url = track.getStreamURL()
            else:
                media = track.media[0]
                part = media.parts[0]
                stream_url = f"{self.base_url}{part.key}?X-Plex-Token={self.token}"

            duration_seconds = int((track.duration or 0) / 1000)
            artist = getattr(track, 'grandparentTitle', None) or getattr(track, 'artist', None)
            album = getattr(track, 'parentTitle', None)
            thumbnail = getattr(track, 'thumbUrl', None) if getattr(track, 'thumb', None) else None
            deep_link = f"{self.base_url}{track.key}?X-Plex-Token={self.token}"

            return {
                'title': track.title,
                'artist': artist,
                'album': album,
                'duration': duration_seconds,
                'thumbnail': thumbnail,
                'stream_url': stream_url,
                'webpage_url': deep_link,
                'rating_key': getattr(track, 'ratingKey', None),
                'library': library.title,
            }

        try:
            return await asyncio.to_thread(_resolve)
        except PlexApiException as exc:
            logger.error(f"Plex query failed: {exc}")
            return None
class Song:
    def __init__(self, source, requester):
        self.source = source
        self.requester = requester
        
    def create_embed(self, automesh_mode=False):
        # Use different colors for automesh mode
        color = 0x9B59B6 if automesh_mode else 0x1DB954  # Purple for automesh, green for normal
        
        embed = discord.Embed(
            title="Now Playing",
            description=f"**{self.source.title}**",
            color=color
        )
        embed.add_field(name="Requested by", value=self.requester.mention, inline=True)

        if hasattr(self.source, 'provider'):
            provider_display = getattr(self.source, 'provider', 'youtube').title()
            if provider_display == 'Plex' and getattr(self.source, 'data', None):
                library = self.source.data.get('library')
                if library:
                    provider_display = f"Plex ({library})"
            embed.add_field(name="Source", value=provider_display, inline=True)
        
        if self.source.duration:
            minutes, seconds = divmod(self.source.duration, 60)
            embed.add_field(name="Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)
        
        if self.source.uploader:
            embed.add_field(name="Uploader", value=self.source.uploader, inline=True)
        
        if self.source.thumbnail:
            embed.set_thumbnail(url=self.source.thumbnail)
        
        if self.source.webpage_url:
            embed.add_field(name="URL", value=f"[Click here]({self.source.webpage_url})", inline=False)
        
        return embed

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.is_playing = False
        self.current_song: Optional[Song] = None
        self.loop_mode = False
        self.automesh_mode = False
        self.stream_mode = False  # Continuous stream mode
        self.current_stream_info = None  # Info about current stream
        self.automesh_queues: Dict[int, deque] = {}  # user_id -> deque of songs
        self.automesh_cycle = deque()  # deque of user_ids for cycling
        self.automesh_last_user = None  # Track last user who had a song played
        self.volume = 0.5  # Store volume setting
        self.shuffle_mode = False  # Track if shuffle is enabled
        self.history = deque(maxlen=50)  # Keep history of played songs for previous functionality
        
    def add_song(self, song: Song):
        if self.automesh_mode:
            user_id = song.requester.id
            # Add song to user's personal queue
            if user_id not in self.automesh_queues:
                self.automesh_queues[user_id] = deque()
                # Add user to cycle if not already there
                if user_id not in self.automesh_cycle:
                    self.automesh_cycle.append(user_id)
                    logger.debug(f"Added user {song.requester.display_name} to automesh cycle")
            
            self.automesh_queues[user_id].append(song)
            logger.debug(f"Added song to {song.requester.display_name}'s automesh queue")
        else:
            self.queue.append(song)
    
    def get_next_song(self) -> Optional[Song]:
        if self.automesh_mode:
            return self._get_next_automesh_song()
        else:
            if self.shuffle_mode and self.queue:
                # Get random song from queue
                queue_list = list(self.queue)
                if queue_list:
                    import random
                    random_song = random.choice(queue_list)
                    self.queue.remove(random_song)
                    return random_song
            elif self.queue:
                return self.queue.popleft()
            return None
    
    def shuffle_queue(self):
        """Shuffle the current queue"""
        if self.queue:
            import random
            queue_list = list(self.queue)
            random.shuffle(queue_list)
            self.queue = deque(queue_list)
    
    def get_previous_song(self) -> Optional[Song]:
        """Get the previous song from history"""
        if self.history:
            return self.history[-1]  # Get most recent song from history
        return None
    
    def add_to_history(self, song: Song):
        """Add a song to the history"""
        if song:
            self.history.append(song)
    
    def _get_next_automesh_song(self) -> Optional[Song]:
        """Get the next song in automesh mode, cycling through users"""
        if not self.automesh_cycle:
            return None
        
        logger.debug(f"Automesh cycle before selection: {[uid for uid in self.automesh_cycle]}")
        logger.debug(f"Last user was: {self.automesh_last_user}")
        
        # Try to find the next user in cycle who has songs
        attempts = 0
        max_attempts = len(self.automesh_cycle)
        
        while attempts < max_attempts:
            # Get next user in cycle
            if not self.automesh_cycle:
                break
                
            user_id = self.automesh_cycle[0]
            self.automesh_cycle.rotate(-1)  # Move to next user
            
            # Check if this user has songs
            if user_id in self.automesh_queues and self.automesh_queues[user_id]:
                song = self.automesh_queues[user_id].popleft()
                self.automesh_last_user = user_id
                logger.debug(f"Selected next automesh song from user {song.requester.display_name} (ID: {user_id})")
                logger.debug(f"Automesh cycle after selection: {[uid for uid in self.automesh_cycle]}")
                return song
            
            attempts += 1
        
        return None
    
    def clear(self):
        # Clean up any downloaded files in the queue
        for song in self.queue:
            if hasattr(song.source, 'cleanup'):
                song.source.cleanup()
        # Clean up automesh queues
        for user_queue in self.automesh_queues.values():
            for song in user_queue:
                if hasattr(song.source, 'cleanup'):
                    song.source.cleanup()
        # Clean up current song
        if self.current_song and hasattr(self.current_song.source, 'cleanup'):
            self.current_song.source.cleanup()
            
        self.queue.clear()
        self.automesh_queues.clear()
        self.automesh_cycle.clear()
        self.current_song = None
        self.is_playing = False
        self.automesh_mode = False
        self.stream_mode = False
        self.automesh_last_user = None
    
    def get_queue_embed(self, guild_name: str) -> discord.Embed:
        # Use different colors for automesh mode
        color = 0x9B59B6 if self.automesh_mode else 0x1DB954  # Purple for automesh, green for normal
        
        embed = discord.Embed(
            title=f"🎵 Music Queue - {guild_name}",
            color=color
        )
        
        if self.automesh_mode:
            embed.title = f"🔀 Automesh Queue - {guild_name}"
        
        if self.current_song:
            current_desc = f"**{self.current_song.source.title}**\nRequested by {self.current_song.requester.mention}"
            
            # Add status indicators
            status_indicators = []
            if self.loop_mode:
                status_indicators.append("🔁 Loop")
            if self.shuffle_mode:
                status_indicators.append("🔀 Shuffle")
            
            if status_indicators:
                current_desc += f"\n{' | '.join(status_indicators)}"
            
            embed.add_field(
                name="🎶 Currently Playing",
                value=current_desc,
                inline=False
            )
        
        if self.automesh_mode:
            # Show automesh queues
            if self.automesh_queues:
                automesh_info = []
                for user_id in self.automesh_cycle:
                    if user_id in self.automesh_queues and self.automesh_queues[user_id]:
                        user_queue = self.automesh_queues[user_id]
                        # Get user name from first song in their queue
                        user_name = list(user_queue)[0].requester.display_name
                        next_song = list(user_queue)[0].source.title
                        automesh_info.append(f"**{user_name}** ({len(user_queue)} songs)\n└ Next: {next_song}")
                
                if automesh_info:
                    embed.add_field(
                        name="🔀 Automesh Cycle",
                        value="\n\n".join(automesh_info[:5]),  # Show first 5 users
                        inline=False
                    )
                    
                    if len(automesh_info) > 5:
                        embed.add_field(
                            name="📝 Note",
                            value=f"... and {len(automesh_info) - 5} more users",
                            inline=False
                        )
                else:
                    embed.add_field(
                        name="🔀 Automesh Cycle",
                        value="No songs in automesh queues",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🔀 Automesh Cycle",
                    value="No users in automesh cycle",
                    inline=False
                )
        else:
            # Show normal queue
            if self.queue:
                queue_list = []
                for i, song in enumerate(list(self.queue)[:10], 1):  # Show first 10 songs
                    queue_list.append(f"{i}. **{song.source.title}** - {song.requester.mention}")
                
                queue_title = f"📋 Up Next ({len(self.queue)} songs)"
                if self.shuffle_mode:
                    queue_title = f"� Up Next - Shuffled ({len(self.queue)} songs)"
                
                embed.add_field(
                    name=queue_title,
                    value="\n".join(queue_list),
                    inline=False
                )
                
                if len(self.queue) > 10:
                    embed.add_field(
                        name="📝 Note",
                        value=f"... and {len(self.queue) - 10} more songs",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="📋 Queue",
                    value="No songs in queue",
                    inline=False
                )
        
        return embed
    
    def toggle_automesh(self) -> bool:
        """Toggle automesh mode and return new state"""
        old_mode = self.automesh_mode
        self.automesh_mode = not self.automesh_mode
        
        if not old_mode and self.automesh_mode:
            # Switching FROM normal TO automesh - reorganize queue with smart distribution
            if self.queue:
                songs_to_distribute = list(self.queue)
                self.queue.clear()
                
                # Initialize automesh queues for all users who have songs
                users_with_songs = set()
                for song in songs_to_distribute:
                    user_id = song.requester.id
                    users_with_songs.add(user_id)
                    if user_id not in self.automesh_queues:
                        self.automesh_queues[user_id] = deque()
                
                # Set up the automesh cycle, ensuring current song's requester is last
                current_requester_id = None
                if self.current_song:
                    current_requester_id = self.current_song.requester.id
                    self.automesh_last_user = current_requester_id
                
                # Add users to cycle, putting current requester at the end
                other_users = [uid for uid in users_with_songs if uid != current_requester_id]
                self.automesh_cycle = deque(other_users)
                if current_requester_id and current_requester_id in users_with_songs:
                    self.automesh_cycle.append(current_requester_id)
                
                logger.debug(f"Automesh cycle order: {[uid for uid in self.automesh_cycle]}")
                if current_requester_id:
                    logger.debug(f"Current requester ({current_requester_id}) placed at end of cycle")
                
                # Distribute songs in a way that prevents large blocks from same user
                # Use a round-robin approach but respect original requesters
                user_counters = {user_id: 0 for user_id in users_with_songs}
                
                for song in songs_to_distribute:
                    original_user = song.requester.id
                    
                    # Find user with lowest song count to maintain balance
                    # Prefer the original requester if they're not too far ahead
                    min_count = min(user_counters.values())
                    original_user_count = user_counters[original_user]
                    
                    # If original user has more than 2 songs ahead of the minimum,
                    # assign to a user with minimum count instead
                    if original_user_count <= min_count + 2:
                        target_user = original_user
                    else:
                        # Find user with minimum count
                        target_user = min(user_counters.keys(), key=lambda u: user_counters[u])
                    
                    self.automesh_queues[target_user].append(song)
                    user_counters[target_user] += 1
        
        elif old_mode and not self.automesh_mode:
            # Switching FROM automesh TO normal - flatten automesh queues to normal queue
            # Keep current order (round-robin through users)
            if self.automesh_queues:
                # Create a flattened queue maintaining the automesh order
                remaining_users = [user_id for user_id in self.automesh_cycle 
                                 if user_id in self.automesh_queues and self.automesh_queues[user_id]]
                
                # Round-robin through users until all songs are moved
                while remaining_users:
                    for user_id in remaining_users[:]:  # Use slice to avoid modification during iteration
                        if user_id in self.automesh_queues and self.automesh_queues[user_id]:
                            song = self.automesh_queues[user_id].popleft()
                            self.queue.append(song)
                            
                            # Remove user from remaining_users if they have no more songs
                            if not self.automesh_queues[user_id]:
                                remaining_users.remove(user_id)
                        else:
                            # This shouldn't happen, but remove user just in case
                            if user_id in remaining_users:
                                remaining_users.remove(user_id)
            
            # Clean up automesh data when disabling
            for user_queue in self.automesh_queues.values():
                for song in user_queue:
                    if hasattr(song.source, 'cleanup'):
                        song.source.cleanup()
            self.automesh_queues.clear()
            self.automesh_cycle.clear()
            self.automesh_last_user = None
    
    def remove_user_from_automesh(self, user_id: int) -> int:
        """Remove a user from automesh and return number of songs removed"""
        songs_removed = 0
        
        if user_id in self.automesh_queues:
            # Clean up songs from this user
            user_queue = self.automesh_queues[user_id]
            for song in user_queue:
                if hasattr(song.source, 'cleanup'):
                    song.source.cleanup()
            songs_removed = len(user_queue)
            del self.automesh_queues[user_id]
        
        # Remove user from cycle
        if user_id in self.automesh_cycle:
            # Convert to list, remove, convert back to deque
            cycle_list = list(self.automesh_cycle)
            cycle_list.remove(user_id)
            self.automesh_cycle = deque(cycle_list)
        
        return songs_removed
    
    def get_automesh_users(self) -> List[int]:
        """Get list of user IDs in automesh cycle"""
        return list(self.automesh_cycle)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_queues: Dict[int, MusicQueue] = {}
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        self.last_music_channels: Dict[int, int] = {}  # guild_id -> channel_id for now playing messages
        self.rating_messages: Dict[int, Dict[str, any]] = {}  # message_id -> {"guild_id": int, "song_url": str, "expires_at": float}
        self.now_playing_messages: Dict[int, int] = {}  # guild_id -> message_id for current now playing messages
        self.global_config = load_global_config()
        self._plex_provider: Optional[PlexMusicProvider] = None
        self._plex_provider_signature: Optional[tuple[str, str, bool, int]] = None
        # Don't start the cleanup task immediately
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        logger.info("Music cog loaded, starting progress update task")
        self.progress_update_task.start()
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        logger.info("Music cog unloading, cleaning up")
        self.progress_update_task.cancel()
        
        # Clean up all music queues and downloaded files
        for music_queue in self.music_queues.values():
            music_queue.clear()
            
        # Clean up rating messages
        self.rating_messages.clear()
        
        # Clean up now playing messages
        self.now_playing_messages.clear()
            
        # Disconnect all voice clients
        for guild_id, voice_client in self.voice_clients.items():
            try:
                if voice_client.is_connected():
                    await voice_client.disconnect()
                    logger.debug(f"Disconnected voice client for guild {guild_id}")
            except Exception as e:
                logger.warning(f"Error disconnecting voice client during unload: {e}")
        self.voice_clients.clear()
    
    @tasks.loop(seconds=10)
    async def progress_update_task(self):
        """Update progress bars for all active now playing messages"""
        try:
            # Update progress for all guilds with active music
            for guild_id in list(self.now_playing_messages.keys()):
                await self.update_now_playing_progress(guild_id)
        except Exception as e:
            logger.error(f"Error in progress update task: {e}")
    
    @progress_update_task.before_loop
    async def before_progress_update(self):
        """Wait for bot to be ready before starting progress updates"""
        await self.bot.wait_until_ready()
    
    def get_music_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = MusicQueue()
        return self.music_queues[guild_id]

    def _reload_global_config(self) -> None:
        self.global_config = load_global_config(refresh=True)

    def get_server_config_value(self, guild_id: int, key: str, default: Any = None) -> Any:
        server_config_cog = self.bot.get_cog('ServerConfig')
        if server_config_cog:
            return server_config_cog.get_config(guild_id, key, default)
        return default

    def get_music_provider_for_guild(self, guild_id: int) -> str:
        self._reload_global_config()
        default_provider = self.global_config.get('music', {}).get('default_provider', 'youtube')
        provider = self.get_server_config_value(guild_id, 'music_provider', default_provider)
        return (provider or 'youtube').lower()

    def get_plex_library_for_guild(self, guild_id: int) -> str:
        override = self.get_server_config_value(guild_id, 'plex_library', None)
        if override:
            return override
        self._reload_global_config()
        return self.global_config.get('plex', {}).get('music_library', 'Music')

    def _get_or_create_plex_provider(self) -> Optional[PlexMusicProvider]:
        self._reload_global_config()
        plex_cfg = self.global_config.get('plex', {})

        if not plex_cfg.get('enabled'):
            return None
        if not plex_cfg.get('base_url') or not plex_cfg.get('token'):
            logger.debug("Plex integration disabled: base_url/token missing")
            return None
        if PlexServer is None:
            logger.warning("plexapi is not installed, cannot enable Plex provider")
            return None

        signature = (
            plex_cfg.get('base_url', ''),
            plex_cfg.get('token', ''),
            bool(plex_cfg.get('allow_transcode', True)),
            int(plex_cfg.get('timeout', 10)),
        )

        if self._plex_provider is None or self._plex_provider_signature != signature:
            try:
                self._plex_provider = PlexMusicProvider(
                    base_url=plex_cfg['base_url'],
                    token=plex_cfg['token'],
                    allow_transcode=plex_cfg.get('allow_transcode', True),
                    timeout=plex_cfg.get('timeout', 10),
                )
                self._plex_provider_signature = signature
            except Exception as exc:
                logger.error(f"Failed to initialise Plex provider: {exc}")
                self._plex_provider = None
                self._plex_provider_signature = None
        return self._plex_provider

    def should_use_plex(self, guild_id: int) -> bool:
        provider = self.get_music_provider_for_guild(guild_id)
        if provider != 'plex':
            return False
        provider_instance = self._get_or_create_plex_provider()
        return provider_instance is not None

    async def create_plex_source(self, query: str, guild_id: int) -> Optional[PlexAudioSource]:
        provider = self._get_or_create_plex_provider()
        if not provider:
            return None

        library_name = self.get_plex_library_for_guild(guild_id)
        metadata = await provider.resolve_track(query, library_name)
        if not metadata:
            return None

        ffmpeg_executable = get_ffmpeg_executable()
        ffmpeg_source = discord.FFmpegPCMAudio(
            metadata['stream_url'],
            executable=ffmpeg_executable,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        )

        metadata['provider'] = 'plex'
        return PlexAudioSource(ffmpeg_source, data=metadata)
    
    async def update_bot_status(self, song: Optional[Song] = None):
        """Update bot's Discord activity status"""
        try:
            if song:
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=song.source.title
                )
                logger.debug(f"Updated bot status to: {song.source.title}")
            else:
                activity = discord.Game(name="Ready to play music!")
                logger.debug("Updated bot status to ready")
            
            await self.bot.change_presence(activity=activity)
        except Exception as e:
            logger.error(f"Error updating bot status: {e}")

    async def cleanup_now_playing_message(self, guild_id: int):
        """Clean up the previous now playing message when a new song starts"""
        try:
            if guild_id in self.now_playing_messages:
                old_message_id = self.now_playing_messages[guild_id]
                channel_id = self.last_music_channels.get(guild_id)
                if channel_id:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        try:
                            old_message = await channel.fetch_message(old_message_id)
                            # First try to clear reactions to clean up the interface
                            try:
                                await old_message.clear_reactions()
                                logger.debug(f"Cleared reactions from old now playing message {old_message_id}")
                            except discord.HTTPException:
                                logger.debug(f"Could not clear reactions from message {old_message_id}")
                            
                            # Then delete the message
                            await old_message.delete()
                            logger.debug(f"Deleted old now playing message {old_message_id}")
                        except discord.NotFound:
                            logger.debug(f"Old now playing message {old_message_id} already deleted")
                        except discord.HTTPException as e:
                            logger.warning(f"Could not delete old now playing message {old_message_id}: {e}")
                        except Exception as e:
                            logger.error(f"Unexpected error deleting old now playing message {old_message_id}: {e}")
                
                # Always remove from tracking dict
                del self.now_playing_messages[guild_id]
                
        except Exception as e:
            logger.error(f"Error cleaning up now playing message: {e}")

    async def cleanup_rating_messages(self, guild_id: int):
        """Clean up rating messages for a specific guild"""
        try:
            current_time = time.time()
            expired_messages = []
            
            # Find expired messages for this guild
            for message_id, data in self.rating_messages.items():
                if data["guild_id"] == guild_id and current_time > data["expires_at"]:
                    expired_messages.append(message_id)
            
            # Clean up expired messages
            for message_id in expired_messages:
                try:
                    channel_id = self.last_music_channels.get(guild_id)
                    if channel_id:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            try:
                                message = await channel.fetch_message(message_id)
                                await message.clear_reactions()
                                logger.debug(f"Cleared reactions from expired rating message {message_id}")
                            except:
                                pass  # Message might be deleted
                    del self.rating_messages[message_id]
                except Exception as e:
                    logger.warning(f"Error cleaning up expired rating message {message_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in cleanup_rating_messages for guild {guild_id}: {e}")

    async def play_next_song(self, guild_id: int, skip_now_playing_message: bool = False):
        """Play the next song in the queue"""
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        # Clean up previous now playing message
        await self.cleanup_now_playing_message(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            logger.debug(f"Voice client not connected for guild {guild_id}")
            return
        
        if music_queue.loop_mode and music_queue.current_song:
            # Loop current song
            try:
                # Create a new source for the same song
                current = music_queue.current_song
                source = await YTDLSource.create_source(
                    None, current.source.webpage_url, loop=self.bot.loop
                )
                source.volume = music_queue.volume
                
                voice_client.play(source, after=lambda e: self.bot.loop.create_task(
                    self.play_next_song(guild_id)
                ) if e is None else logger.error(f"Player error: {e}"))
                
                music_queue.is_playing = True
                await self.update_bot_status(current)
                
                # Send now playing message if not skipped
                if not skip_now_playing_message:
                    await self.send_now_playing_message(guild_id, current)
                    
            except Exception as e:
                logger.error(f"Error looping song: {e}")
                music_queue.loop_mode = False  # Disable loop on error
                await self.play_next_song(guild_id)
            return
        
        # Get next song
        next_song = music_queue.get_next_song()
        
        if next_song is None:
            # No more songs in queue
            music_queue.is_playing = False
            # Add current song to history before clearing it
            if music_queue.current_song:
                music_queue.add_to_history(music_queue.current_song)
            music_queue.current_song = None
            await self.update_bot_status()
            return
        
        try:
            # Check if this is a minimal playlist entry that needs to be resolved
            if next_song.source.original is None and hasattr(next_song.source, 'webpage_url'):
                # This is a playlist entry that needs to be resolved to an actual audio source
                logger.debug(f"Resolving playlist entry: {next_song.source.title}")
                try:
                    # Create a proper audio source from the playlist entry
                    resolved_source = await YTDLSource.create_source(
                        None, next_song.source.webpage_url, loop=self.bot.loop
                    )
                    # Replace the minimal source with the resolved one
                    next_song.source = resolved_source
                except Exception as resolve_error:
                    logger.error(f"Failed to resolve playlist entry: {resolve_error}")
                    # Skip this song and try the next one
                    await self.play_next_song(guild_id)
                    return
            
            # Set volume from queue settings
            next_song.source.volume = music_queue.volume
            
            # Play the song
            def after_playing(error):
                if error is None:
                    self.bot.loop.create_task(self.play_next_song(guild_id))
                else:
                    logger.error(f"Player error: {error}")
            
            voice_client.play(next_song.source, after=after_playing)
            
            # Add previous song to history before setting new current song
            if music_queue.current_song:
                music_queue.add_to_history(music_queue.current_song)
            
            music_queue.current_song = next_song
            music_queue.is_playing = True
            # Reset song start time for progress tracking
            music_queue.song_start_time = time.time()
            
            # Record the song play
            try:
                db = MusicEloDatabase()
                url = getattr(next_song.source, 'webpage_url', None) or getattr(next_song.source, 'url', None)
                if url:
                    # Get or create song in database
                    song_row = db.get_song_by_url(url)
                    if not song_row:
                        # Add the song to database
                        song_id = db.add_song(
                            url=url,
                            title=next_song.source.title,
                            artist=getattr(next_song.source, 'uploader', None),
                            duration=getattr(next_song.source, 'duration', None),
                            thumbnail_url=getattr(next_song.source, 'thumbnail', None)
                        )
                    else:
                        song_id = song_row[0]
                    
                    # Record the play
                    if song_id:
                        db.add_song_play(song_id, guild_id, next_song.requester.id)
                        logger.debug(f"Recorded song play: {next_song.source.title}")
            except Exception as e:
                logger.error(f"Error recording song play: {e}")
            
            await self.update_bot_status(next_song)
            
            # Send now playing message if not skipped
            if not skip_now_playing_message:
                await self.send_now_playing_message(guild_id, next_song)
                
        except Exception as e:
            logger.error(f"Error playing next song: {e}")
            # Try next song
            await self.play_next_song(guild_id)

    async def play_previous_song(self, guild_id: int):
        """Play the previous song from history"""
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            logger.debug(f"Voice client not connected for guild {guild_id}")
            return False
        
        previous_song = music_queue.get_previous_song()
        if not previous_song:
            logger.debug(f"No previous song available for guild {guild_id}")
            return False
        
        try:
            # Remove the previous song from history since we're going to play it
            music_queue.history.pop()
            
            # Stop current song
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            
            # Add current song back to the front of the queue
            if music_queue.current_song:
                if music_queue.automesh_mode:
                    user_id = music_queue.current_song.requester.id
                    if user_id in music_queue.automesh_queues:
                        music_queue.automesh_queues[user_id].appendleft(music_queue.current_song)
                else:
                    music_queue.queue.appendleft(music_queue.current_song)
            
            # Create a new source for the previous song
            source = await YTDLSource.create_source(
                None, previous_song.source.webpage_url, loop=self.bot.loop
            )
            source.volume = music_queue.volume
            
            # Play the previous song
            def after_playing(error):
                if error is None:
                    self.bot.loop.create_task(self.play_next_song(guild_id))
                else:
                    logger.error(f"Player error: {error}")
            
            voice_client.play(source, after=after_playing)
            
            music_queue.current_song = previous_song
            music_queue.is_playing = True
            music_queue.song_start_time = time.time()
            
            await self.update_bot_status(previous_song)
            await self.send_now_playing_message(guild_id, previous_song)
            
            return True
            
        except Exception as e:
            logger.error(f"Error playing previous song: {e}")
            return False

    async def restart_current_song(self, guild_id: int):
        """Restart the current song from the beginning"""
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if not voice_client or not voice_client.is_connected() or not music_queue.current_song:
            return False
        
        try:
            # Stop current playback
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            
            current_song = music_queue.current_song
            
            # Create a new source for the current song
            source = await YTDLSource.create_source(
                None, current_song.source.webpage_url, loop=self.bot.loop
            )
            source.volume = music_queue.volume
            
            # Play the restarted song
            def after_playing(error):
                if error is None:
                    self.bot.loop.create_task(self.play_next_song(guild_id))
                else:
                    logger.error(f"Player error: {error}")
            
            voice_client.play(source, after=after_playing)
            
            # Update the current song source and reset timing
            music_queue.current_song.source = source
            music_queue.is_playing = True
            music_queue.song_start_time = time.time()
            
            # Clear any pause time
            if hasattr(music_queue, 'pause_time'):
                delattr(music_queue, 'pause_time')
            
            await self.update_bot_status(current_song)
            await self.send_now_playing_message(guild_id, current_song)
            
            return True
            
        except Exception as e:
            logger.error(f"Error restarting current song: {e}")
            return False

    async def send_now_playing_message(self, guild_id: int, song: Song):
        """Send a now playing message with music controls and progress bar"""
        channel_id = self.last_music_channels.get(guild_id)
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        try:
            # Clean up old now playing message first
            await self.cleanup_now_playing_message(guild_id)
            
            music_queue = self.get_music_queue(guild_id)
            
            # Mark when this song started
            music_queue.song_start_time = time.time()
            
            # Use different colors for automesh mode
            color = 0x9B59B6 if music_queue.automesh_mode else 0x1DB954  # Purple for automesh, green for normal
            
            # Create custom embed with everything in description
            embed = discord.Embed(
                title="🎵 Now Playing",
                color=color
            )
            
            # Build fancy description with all information
            total_duration = getattr(song.source, 'duration', 0)
            progress_bar = self.create_progress_bar(0, total_duration, False)
            volume_percentage = int(music_queue.volume * 100)
            
            # Format duration
            if total_duration:
                minutes, seconds = divmod(total_duration, 60)
                duration_str = f"{int(minutes)}:{int(seconds):02d}"
            else:
                duration_str = "Live Stream"
            
            # Build description with fancy spacing and formatting
            description = f"**{song.source.title}**\n"
            description += f"{progress_bar}\n\n"
            description += f"**🎤 Requested by:** {song.requester.mention}\n"
            description += f"**🔊 Volume:** {volume_percentage}%"
            
            if song.source.uploader:
                description += f"\n**📺 Channel:** {song.source.uploader}"
            
            if song.source.webpage_url:
                description += f"\n**🔗 Link:** [Watch on YouTube]({song.source.webpage_url})"
            
            # Add mode indicator
            if music_queue.automesh_mode:
                description += f"\n\n� **Mode:** Automesh"
            else:
                description += f"\n\n📋 **Mode:** Normal Queue"
            
            embed.description = description
            
            # Set thumbnail if available
            if song.source.thumbnail:
                embed.set_thumbnail(url=song.source.thumbnail)
            
            message = await channel.send(embed=embed)
            
            # Store this as the current now playing message
            self.now_playing_messages[guild_id] = message.id
            
            # Add music control reactions
            control_emojis = ['⏮️', '🔄', '⏸️', '▶️', '⏭️', '🔀', '🔉', '🔊']
            for emoji in control_emojis:
                try:
                    await message.add_reaction(emoji)
                    # Small delay to prevent rate limiting
                    await asyncio.sleep(0.1)
                except discord.HTTPException:
                    logger.warning(f"Failed to add control reaction {emoji}")
                    continue
                except Exception as e:
                    logger.error(f"Error adding control reaction {emoji}: {e}")
                    break
                        
        except Exception as e:
            logger.error(f"Error sending now playing message: {e}")

    def create_progress_bar(self, current_time: float, total_time: float, is_paused: bool = False, length: int = 20) -> str:
        """Create a visual progress bar for the current song"""
        if total_time <= 0:
            if is_paused:
                return "⏸️ ━━━━━━━━━━━━━━━━━━━━ Live Stream (Paused)"
            return "🎵 ━━━━━━━━━━━━━━━━━━━━ Live Stream"
        
        # Calculate progress percentage
        progress = min(current_time / total_time, 1.0)
        filled_length = int(length * progress)
        
        # Create progress bar with different characters
        if is_paused:
            bar = "━" * filled_length + "⏸️" + "─" * (length - filled_length - 1)
            prefix = "⏸️"
        else:
            bar = "━" * filled_length + "○" + "─" * (length - filled_length - 1)
            prefix = "🎵"
        
        # Format time display
        current_min, current_sec = divmod(int(current_time), 60)
        total_min, total_sec = divmod(int(total_time), 60)
        
        time_str = f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}"
        
        suffix = " (Paused)" if is_paused else ""
        
        return f"{prefix} {bar} {time_str}{suffix}"

    def get_song_position(self, guild_id: int) -> float:
        """Get the current position in the song"""
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if not voice_client or not music_queue.current_song:
            return 0.0
        
        # Get when the song started
        if not hasattr(music_queue, 'song_start_time'):
            music_queue.song_start_time = time.time()
        
        # If paused, use pause time instead of current time
        if voice_client.is_paused() and hasattr(music_queue, 'pause_time'):
            elapsed = music_queue.pause_time - music_queue.song_start_time
        elif voice_client.is_playing():
            elapsed = time.time() - music_queue.song_start_time
        else:
            elapsed = 0.0
        
        return max(0.0, elapsed)

    async def update_now_playing_progress(self, guild_id: int):
        """Update the progress bar for the current now playing message"""
        try:
            music_queue = self.get_music_queue(guild_id)
            voice_client = self.voice_clients.get(guild_id)
            
            if (not voice_client or not music_queue.current_song or 
                guild_id not in self.now_playing_messages):
                return
            
            channel_id = self.last_music_channels.get(guild_id)
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message_id = self.now_playing_messages[guild_id]
            try:
                message = await channel.fetch_message(message_id)
            except (discord.NotFound, discord.HTTPException):
                # Message was deleted, clean up
                del self.now_playing_messages[guild_id]
                return
            
            # Get current song info
            song = music_queue.current_song
            current_pos = self.get_song_position(guild_id)
            total_duration = getattr(song.source, 'duration', 0)
            is_paused = voice_client.is_paused()
            volume_percentage = int(music_queue.volume * 100)
            
            # Use different colors for automesh mode
            color = 0x9B59B6 if music_queue.automesh_mode else 0x1DB954  # Purple for automesh, green for normal
            
            # Create updated embed with everything in description
            embed = discord.Embed(
                title="🎵 Now Playing",
                color=color
            )
            
            # Format duration
            if total_duration:
                minutes, seconds = divmod(total_duration, 60)
                duration_str = f"{int(minutes)}:{int(seconds):02d}"
            else:
                duration_str = "Live Stream"
            
            # Build description with fancy spacing and formatting
            progress_bar = self.create_progress_bar(current_pos, total_duration, is_paused)
            description = f"**{song.source.title}**\n"
            description += f"{progress_bar}\n\n"
            description += f"**🎤 Requested by:** {song.requester.mention}\n"
            description += f"**🔊 Volume:** {volume_percentage}%"
            
            if song.source.uploader:
                description += f"\n**📺 Channel:** {song.source.uploader}"
            
            if song.source.webpage_url:
                description += f"\n**🔗 Link:** [Watch on YouTube]({song.source.webpage_url})"
            
            # Add mode indicator
            mode_parts = []
            if music_queue.automesh_mode:
                mode_parts.append("🔀 Automesh")
            else:
                mode_parts.append("� Normal Queue")
            
            if music_queue.shuffle_mode:
                mode_parts.append("🔀 Shuffle")
            if music_queue.loop_mode:
                mode_parts.append("🔁 Loop")
            
            description += f"\n\n**Mode:** {' | '.join(mode_parts)}"
            
            embed.description = description
            
            # Set thumbnail if available
            if song.source.thumbnail:
                embed.set_thumbnail(url=song.source.thumbnail)
            
            # Update the message
            await message.edit(embed=embed)
            
        except Exception as e:
            logger.error(f"Error updating now playing progress: {e}")

    # --- Core Music Commands ---
    @commands.hybrid_command(name='play', aliases=['p'])
    @app_commands.describe(query="Song name, YouTube URL, or YouTube playlist URL")
    async def play(self, ctx, *, query: str):
        """Play a song or add it to the queue"""
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel to use this command!")
            return
        
        guild_id = ctx.guild.id
        voice_channel = ctx.author.voice.channel
        music_queue = self.get_music_queue(guild_id)
        
        # Store the channel for now playing messages
        self.last_music_channels[guild_id] = ctx.channel.id
        
        # Connect to voice channel if not already connected
        if guild_id not in self.voice_clients or not self.voice_clients[guild_id].is_connected():
            try:
                voice_client = await asyncio.wait_for(
                    voice_channel.connect(timeout=10.0, reconnect=True),
                    timeout=15.0
                )
                self.voice_clients[guild_id] = voice_client
                await ctx.send(f"🔗 Connected to **{voice_channel.name}**")
            except Exception as e:
                await ctx.send(f"❌ Failed to connect to voice channel: {str(e)}")
                return
        
        # Check if this looks like a playlist
        is_playlist = 'playlist' in query.lower() or 'list=' in query
        
        try:
            if is_playlist:
                # Handle playlist
                if ctx.interaction:
                    await ctx.defer()
                
                await ctx.send(f"🔍 Extracting playlist: **{query}**...")
                
                # Extract playlist
                source_info = await YTDLSource.create_source(
                    ctx, query, loop=self.bot.loop, extract_playlist=True
                )
                
                if isinstance(source_info, list):
                    # Multiple songs from playlist
                    added_count = 0
                    failed_count = 0
                    
                    for i, entry_data in enumerate(source_info[:50]):  # Limit to 50 songs
                        try:
                            # Create a YTDLSource from the entry data
                            # We'll create a minimal source without downloading
                            # Create a dummy audio source (None) since we're not playing yet
                            source = YTDLSource.__new__(YTDLSource)
                            source.data = entry_data
                            source.title = entry_data.get('title', 'Unknown')
                            source.url = entry_data.get('url', '')
                            source.duration = entry_data.get('duration')
                            source.thumbnail = entry_data.get('thumbnail')  # This will be None if not present
                            source.uploader = entry_data.get('uploader')
                            source.webpage_url = entry_data.get('webpage_url', entry_data.get('url', ''))
                            source.provider = entry_data.get('provider', 'youtube')
                            source.downloaded_file = None
                            source.original = None  # Set to None for playlist entries, will be created when played
                            source.volume = 0.5  # Set default volume
                            
                            song = Song(source, ctx.author)
                            music_queue.add_song(song)
                            added_count += 1
                            
                            if i % 10 == 0 and i > 0:
                                await ctx.edit_original_response(
                                    content=f"🎵 Processing playlist... {i}/{len(source_info[:50])} songs added"
                                ) if ctx.interaction else None
                                
                        except Exception as e:
                            logger.warning(f"Failed to add playlist song: {e}")
                            failed_count += 1
                            continue
                    
                    embed = discord.Embed(
                        title="📋 Playlist Added",
                        description=f"Added {added_count} songs from playlist to the queue",
                        color=0x1DB954
                    )
                    embed.add_field(name="Successfully Added", value=str(added_count), inline=True)
                    if failed_count > 0:
                        embed.add_field(name="Failed to Add", value=str(failed_count), inline=True)
                    embed.add_field(name="Queue Mode", value="Automesh" if music_queue.automesh_mode else "Normal", inline=True)
                    
                    if ctx.interaction:
                        await ctx.edit_original_response(content="", embed=embed)
                    else:
                        await ctx.send(embed=embed)
                else:
                    # Single song
                    song = Song(source_info, ctx.author)
                    music_queue.add_song(song)
                    
                    embed = discord.Embed(
                        title="🎵 Song Added to Queue",
                        description=f"**{source_info.title}**",
                        color=0x1DB954
                    )
                    embed.add_field(name="Requested by", value=ctx.author.mention, inline=True)
                    embed.add_field(name="Queue Position", value=f"#{len(music_queue.queue)}", inline=True)
                    
                    if source_info.thumbnail:
                        embed.set_thumbnail(url=source_info.thumbnail)
                    
                    if ctx.interaction:
                        await ctx.edit_original_response(content="", embed=embed)
                    else:
                        await ctx.send(embed=embed)
            else:
                # Handle single song
                provider_preference = self.get_music_provider_for_guild(guild_id)
                use_plex = provider_preference == 'plex' and self.should_use_plex(guild_id)
                provider_label = "Plex" if use_plex else "YouTube"
                status_message = await ctx.send(f"🔍 Searching {provider_label} for: **{query}**...")

                source = None
                used_provider = 'plex' if use_plex else provider_preference

                if use_plex:
                    source = await self.create_plex_source(query, guild_id)
                    if source is None:
                        used_provider = 'youtube'
                        try:
                            await status_message.edit(content=f"⚠️ Plex couldn't find **{query}**. Searching YouTube instead...")
                        except discord.HTTPException:
                            await ctx.send(f"⚠️ Plex couldn't find **{query}**. Searching YouTube instead...")
                else:
                    used_provider = 'youtube'

                if source is None:
                    source = await YTDLSource.create_source(ctx, query, loop=self.bot.loop)
                    used_provider = 'youtube'

                song = Song(source, ctx.author)
                music_queue.add_song(song)
                
                embed = discord.Embed(
                    title="🎵 Song Added to Queue",
                    description=f"**{source.title}**",
                    color=0x1DB954
                )
                embed.add_field(name="Requested by", value=ctx.author.mention, inline=True)
                
                # Calculate queue position based on mode
                if music_queue.automesh_mode:
                    user_queue_size = len(music_queue.automesh_queues.get(ctx.author.id, []))
                    embed.add_field(name="Your Queue Position", value=f"#{user_queue_size}", inline=True)
                else:
                    embed.add_field(name="Queue Position", value=f"#{len(music_queue.queue)}", inline=True)
                
                if source.duration:
                    minutes, seconds = divmod(source.duration, 60)
                    embed.add_field(name="Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)
                
                provider_display = used_provider.title()
                if used_provider == 'plex' and getattr(source, 'data', None):
                    library = source.data.get('library')
                    if library:
                        provider_display = f"Plex ({library})"
                embed.add_field(name="Source", value=provider_display, inline=True)

                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)

                try:
                    await status_message.edit(content="", embed=embed)
                except discord.HTTPException:
                    await ctx.send(embed=embed)
            
            # Start playing if nothing is currently playing
            if not music_queue.is_playing:
                await self.play_next_song(guild_id)
                
        except Exception as e:
            logger.error(f"Error in play command: {e}")
            await ctx.send(f"❌ Failed to play song: {str(e)}")

    @commands.hybrid_command(name='dbstats')
    @commands.has_permissions(administrator=True)
    async def database_stats(self, ctx):
        """Show database statistics for debugging (Admin only)"""
        guild_id = ctx.guild.id
        db = MusicEloDatabase()
        
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        try:
            # Count total songs
            cursor.execute("SELECT COUNT(*) FROM songs")
            total_songs = cursor.fetchone()[0]
            
            # Count songs with ratings in this guild
            cursor.execute("SELECT COUNT(DISTINCT sr.song_id) FROM song_ratings sr WHERE sr.guild_id = ?", (guild_id,))
            rated_songs_count = cursor.fetchone()[0]
            
            # Count total ratings in this guild
            cursor.execute("SELECT COUNT(*) FROM song_ratings WHERE guild_id = ?", (guild_id,))
            total_ratings = cursor.fetchone()[0]
            
            # Get average rating for this guild
            cursor.execute("SELECT AVG(rating) FROM song_ratings WHERE guild_id = ?", (guild_id,))
            avg_rating_result = cursor.fetchone()[0]
            avg_rating = avg_rating_result if avg_rating_result else 0
            
            embed = discord.Embed(
                title="🗃️ Database Statistics",
                color=0x1DB954
            )
            embed.add_field(name="Total Songs in Database", value=str(total_songs), inline=True)
            embed.add_field(name="Rated Songs (This Server)", value=str(rated_songs_count), inline=True)
            embed.add_field(name="Total Ratings (This Server)", value=str(total_ratings), inline=True)
            embed.add_field(name="Average Rating (This Server)", value=f"{avg_rating:.2f}/5.0" if avg_rating > 0 else "No ratings", inline=True)
            
            await ctx.send(embed=embed)
            
        finally:
            conn.close()

    @commands.hybrid_command(name='volume', aliases=['v'])
    @app_commands.describe(volume="Volume level (0-100). Leave empty to show current volume.")
    async def volume(self, ctx, volume: int = None):
        """Set or display the music volume (0-100%)"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if volume is None:
            # Show current volume
            current_volume = int(music_queue.volume * 100)
            embed = discord.Embed(
                title="🔊 Current Volume",
                description=f"Volume is set to **{current_volume}%**",
                color=0x1DB954
            )
            await ctx.send(embed=embed)
            return
        
        # Validate volume range
        if volume < 0 or volume > 100:
            await ctx.send("❌ Volume must be between 0 and 100!")
            return
        
        # Convert percentage to decimal
        volume_decimal = volume / 100.0
        
        # Update queue volume setting
        music_queue.volume = volume_decimal
        
        # Update current song volume if playing
        if voice_client and voice_client.source and hasattr(voice_client.source, 'volume'):
            voice_client.source.volume = volume_decimal
        
        # Send confirmation
        embed = discord.Embed(
            title="🔊 Volume Updated",
            description=f"Volume set to **{volume}%**",
            color=0x00FF00
        )
        
        # Add volume bar visualization
        filled_blocks = int(volume / 5)  # 20 blocks for 100%
        empty_blocks = 20 - filled_blocks
        volume_bar = "█" * filled_blocks + "░" * empty_blocks
        embed.add_field(name="Volume Bar", value=f"`{volume_bar}` {volume}%", inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='shuffle')
    async def shuffle(self, ctx):
        """Shuffle the music queue (works with both regular queue and automesh mode)"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        if music_queue.automesh_mode:
            # Shuffle automesh queues
            shuffled_users = 0
            total_songs = 0
            
            for user_id, user_queue in music_queue.automesh_queues.items():
                if len(user_queue) > 1:  # Only shuffle if there's more than 1 song
                    # Convert deque to list, shuffle, convert back to deque
                    songs_list = list(user_queue)
                    import random
                    random.shuffle(songs_list)
                    music_queue.automesh_queues[user_id] = deque(songs_list)
                    shuffled_users += 1
                total_songs += len(user_queue)
            
            if shuffled_users == 0:
                await ctx.send("❌ No user queues to shuffle! Add more songs first.")
                return
            
            embed = discord.Embed(
                title="🔀 Automesh Queues Shuffled",
                description=f"Shuffled queues for **{shuffled_users}** users",
                color=0x9B59B6
            )
            embed.add_field(name="Total Songs", value=str(total_songs), inline=True)
            embed.add_field(name="Users Affected", value=str(shuffled_users), inline=True)
            embed.add_field(name="Mode", value="🔀 Automesh", inline=True)
            
        else:
            # Shuffle regular queue
            if len(music_queue.queue) <= 1:
                await ctx.send("❌ Not enough songs in queue to shuffle! Add more songs first.")
                return
            
            # Convert deque to list, shuffle, convert back to deque
            songs_list = list(music_queue.queue)
            import random
            random.shuffle(songs_list)
            music_queue.queue = deque(songs_list)
            
            embed = discord.Embed(
                title="🔀 Queue Shuffled",
                description=f"Shuffled **{len(songs_list)}** songs in the queue",
                color=0x1DB954
            )
            embed.add_field(name="Songs Shuffled", value=str(len(songs_list)), inline=True)
            embed.add_field(name="Mode", value="📋 Normal Queue", inline=True)
            
            # Show first few songs after shuffle
            if len(songs_list) > 0:
                next_songs = []
                for i, song in enumerate(list(music_queue.queue)[:3]):
                    next_songs.append(f"{i+1}. {song.source.title}")
                embed.add_field(
                    name="Next Songs",
                    value='\n'.join(next_songs),
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skip the current song"""
        guild_id = ctx.guild.id
        voice_client = self.voice_clients.get(guild_id)
        music_queue = self.get_music_queue(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Not connected to a voice channel!")
            return
        
        if not music_queue.current_song:
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        current_song = music_queue.current_song
        
        # Stop current song (this will trigger play_next_song)
        voice_client.stop()
        
        embed = discord.Embed(
            title="⏭️ Song Skipped",
            description=f"Skipped **{current_song.source.title}**",
            color=0x1DB954
        )
        embed.add_field(name="Requested by", value=current_song.requester.mention, inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='stop')
    async def stop(self, ctx):
        """Stop playback and clear the queue"""
        guild_id = ctx.guild.id
        voice_client = self.voice_clients.get(guild_id)
        music_queue = self.get_music_queue(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Not connected to a voice channel!")
            return
        
        # Stop playback
        voice_client.stop()
        
        # Clear queue and current song
        music_queue.clear()
        music_queue.current_song = None
        music_queue.is_playing = False
        
        # Clean up now playing message
        await self.cleanup_now_playing_message(guild_id)
        
        # Update bot status
        await self.update_bot_status()
        
        embed = discord.Embed(
            title="⏹️ Playback Stopped",
            description="Stopped playback and cleared the queue",
            color=0xFF6B6B
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='pause')
    async def pause(self, ctx):
        """Pause the current song"""
        guild_id = ctx.guild.id
        voice_client = self.voice_clients.get(guild_id)
        music_queue = self.get_music_queue(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Not connected to a voice channel!")
            return
        
        if not voice_client.is_playing():
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        if voice_client.is_paused():
            await ctx.send("❌ Playback is already paused!")
            return
        
        voice_client.pause()
        music_queue.pause_time = time.time()
        
        embed = discord.Embed(
            title="⏸️ Playback Paused",
            description=f"Paused **{music_queue.current_song.source.title}**",
            color=0xFFD700
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='resume')
    async def resume(self, ctx):
        """Resume paused playback"""
        guild_id = ctx.guild.id
        voice_client = self.voice_clients.get(guild_id)
        music_queue = self.get_music_queue(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            await ctx.send("❌ Not connected to a voice channel!")
            return
        
        if not voice_client.is_paused():
            await ctx.send("❌ Playback is not paused!")
            return
        
        voice_client.resume()
        
        # Adjust song start time for the pause duration
        if hasattr(music_queue, 'pause_time') and hasattr(music_queue, 'song_start_time'):
            pause_duration = time.time() - music_queue.pause_time
            music_queue.song_start_time += pause_duration
            delattr(music_queue, 'pause_time')
        
        embed = discord.Embed(
            title="▶️ Playback Resumed",
            description=f"Resumed **{music_queue.current_song.source.title}**",
            color=0x00FF00
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='queue', aliases=['q'])
    @app_commands.describe(page="Page number (default 1)")
    async def queue(self, ctx, page: int = 1):
        """Show the current music queue"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        # Determine if we're in automesh mode
        if music_queue.automesh_mode:
            # Show automesh queues
            total_songs = sum(len(queue) for queue in music_queue.automesh_queues.values())
            
            if total_songs == 0:
                embed = discord.Embed(
                    title="📋 Queue (Automesh Mode)",
                    description="No songs in any user queues",
                    color=0x9B59B6
                )
                if music_queue.current_song:
                    embed.add_field(
                        name="🎵 Currently Playing",
                        value=f"**{music_queue.current_song.source.title}**\nRequested by {music_queue.current_song.requester.mention}",
                        inline=False
                    )
                await ctx.send(embed=embed)
                return
            
            embed = discord.Embed(
                title="📋 Queue (Automesh Mode)",
                description=f"Total songs: **{total_songs}** across **{len(music_queue.automesh_queues)}** users",
                color=0x9B59B6
            )
            
            # Show current song
            if music_queue.current_song:
                embed.add_field(
                    name="🎵 Currently Playing",
                    value=f"**{music_queue.current_song.source.title}**\nRequested by {music_queue.current_song.requester.mention}",
                    inline=False
                )
            
            # Show each user's queue
            for user_id, user_queue in music_queue.automesh_queues.items():
                if len(user_queue) > 0:
                    user = self.bot.get_user(user_id)
                    user_name = user.display_name if user else f"User {user_id}"
                    
                    queue_text = []
                    for i, song in enumerate(list(user_queue)[:5]):  # Show first 5 songs
                        queue_text.append(f"{i+1}. {song.source.title}")
                    
                    if len(user_queue) > 5:
                        queue_text.append(f"... and {len(user_queue) - 5} more")
                    
                    embed.add_field(
                        name=f"🎤 {user_name} ({len(user_queue)} songs)",
                        value='\n'.join(queue_text),
                        inline=True
                    )
        else:
            # Show regular queue
            queue_length = len(music_queue.queue)
            
            if queue_length == 0:
                embed = discord.Embed(
                    title="📋 Queue",
                    description="No songs in queue",
                    color=0x1DB954
                )
                if music_queue.current_song:
                    embed.add_field(
                        name="🎵 Currently Playing",
                        value=f"**{music_queue.current_song.source.title}**\nRequested by {music_queue.current_song.requester.mention}",
                        inline=False
                    )
                await ctx.send(embed=embed)
                return
            
            # Pagination
            per_page = 10
            total_pages = (queue_length + per_page - 1) // per_page
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            embed = discord.Embed(
                title="📋 Queue",
                description=f"Page {page}/{total_pages} • {queue_length} songs total",
                color=0x1DB954
            )
            
            # Show current song
            if music_queue.current_song:
                embed.add_field(
                    name="🎵 Currently Playing",
                    value=f"**{music_queue.current_song.source.title}**\nRequested by {music_queue.current_song.requester.mention}",
                    inline=False
                )
            
            # Show queue songs
            queue_list = list(music_queue.queue)
            queue_text = []
            for i, song in enumerate(queue_list[start_idx:end_idx], start=start_idx + 1):
                duration = ""
                if hasattr(song.source, 'duration') and song.source.duration:
                    minutes, seconds = divmod(song.source.duration, 60)
                    duration = f" [{int(minutes)}:{int(seconds):02d}]"
                
                queue_text.append(f"{i}. **{song.source.title}**{duration}\n    Requested by {song.requester.mention}")
            
            if queue_text:
                embed.add_field(
                    name="Up Next",
                    value='\n'.join(queue_text),
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def nowplaying(self, ctx):
        """Show information about the currently playing song"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if not music_queue.current_song:
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        song = music_queue.current_song
        current_pos = self.get_song_position(guild_id)
        total_duration = getattr(song.source, 'duration', 0)
        is_paused = voice_client and voice_client.is_paused()
        volume_percentage = int(music_queue.volume * 100)
        
        # Create embed
        color = 0x9B59B6 if music_queue.automesh_mode else 0x1DB954
        embed = discord.Embed(
            title="🎵 Now Playing",
            color=color
        )
        
        # Progress bar
        progress_bar = self.create_progress_bar(current_pos, total_duration, is_paused)
        
        # Build description
        description = f"**{song.source.title}**\n{progress_bar}\n\n"
        description += f"**🎤 Requested by:** {song.requester.mention}\n"
        description += f"**🔊 Volume:** {volume_percentage}%"
        
        if song.source.uploader:
            description += f"\n**📺 Channel:** {song.source.uploader}"
        
        if song.source.webpage_url:
            description += f"\n**🔗 Link:** [Watch on YouTube]({song.source.webpage_url})"
        
        # Mode indicators
        mode_parts = []
        if music_queue.automesh_mode:
            mode_parts.append("🔀 Automesh")
        else:
            mode_parts.append("📋 Normal Queue")
        
        if music_queue.shuffle_mode:
            mode_parts.append("🔀 Shuffle")
        if music_queue.loop_mode:
            mode_parts.append("🔁 Loop")
        
        description += f"\n\n**Mode:** {' | '.join(mode_parts)}"
        
        embed.description = description
        
        # Set thumbnail
        if song.source.thumbnail:
            embed.set_thumbnail(url=song.source.thumbnail)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='previous', aliases=['prev'])
    async def previous(self, ctx):
        """Play the previous song from history"""
        guild_id = ctx.guild.id
        result = await self.play_previous_song(guild_id)
        
        if result:
            embed = discord.Embed(
                title="⏮️ Playing Previous Song",
                description="Successfully switched to the previous song",
                color=0x00FF00
            )
        else:
            embed = discord.Embed(
                title="❌ No Previous Song",
                description="No previous song available in history",
                color=0xFF6B6B
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='restart')
    async def restart(self, ctx):
        """Restart the current song from the beginning"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        if not music_queue.current_song:
            await ctx.send("❌ Nothing is currently playing!")
            return
        
        result = await self.restart_current_song(guild_id)
        
        if result:
            embed = discord.Embed(
                title="🔄 Song Restarted",
                description=f"Restarted **{music_queue.current_song.source.title}**",
                color=0x00FF00
            )
        else:
            embed = discord.Embed(
                title="❌ Restart Failed",
                description="Failed to restart the current song",
                color=0xFF6B6B
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='clear')
    async def clear(self, ctx):
        """Clear the music queue"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        if music_queue.automesh_mode:
            total_songs = sum(len(queue) for queue in music_queue.automesh_queues.values())
            if total_songs == 0:
                await ctx.send("❌ No songs in queue to clear!")
                return
            
            music_queue.automesh_queues.clear()
            
            embed = discord.Embed(
                title="🗑️ Queue Cleared",
                description=f"Cleared all automesh queues ({total_songs} songs)",
                color=0x9B59B6
            )
        else:
            if len(music_queue.queue) == 0:
                await ctx.send("❌ No songs in queue to clear!")
                return
            
            queue_length = len(music_queue.queue)
            music_queue.queue.clear()
            
            embed = discord.Embed(
                title="🗑️ Queue Cleared",
                description=f"Cleared {queue_length} songs from the queue",
                color=0x1DB954
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='loop')
    async def loop(self, ctx):
        """Toggle loop mode for the current song"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        # Toggle loop mode
        music_queue.loop_mode = not music_queue.loop_mode
        
        embed = discord.Embed(
            title="🔁 Loop Mode",
            description=f"Loop mode **{'enabled' if music_queue.loop_mode else 'disabled'}**",
            color=0x00FF00 if music_queue.loop_mode else 0xFF6B6B
        )
        
        if music_queue.loop_mode and music_queue.current_song:
            embed.add_field(
                name="Current Song",
                value=f"**{music_queue.current_song.source.title}** will loop",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='move')
    @app_commands.describe(
        from_pos="Position of song to move (1-based)",
        to_pos="New position for the song (1-based)"
    )
    async def move(self, ctx, from_pos: int, to_pos: int):
        """Move a song to a different position in the queue"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        if music_queue.automesh_mode:
            await ctx.send("❌ Move command is not available in automesh mode!")
            return
        
        queue_length = len(music_queue.queue)
        
        if queue_length == 0:
            await ctx.send("❌ No songs in queue to move!")
            return
        
        # Validate positions
        if from_pos < 1 or from_pos > queue_length:
            await ctx.send(f"❌ Invalid source position! Must be between 1 and {queue_length}")
            return
        
        if to_pos < 1 or to_pos > queue_length:
            await ctx.send(f"❌ Invalid target position! Must be between 1 and {queue_length}")
            return
        
        if from_pos == to_pos:
            await ctx.send("❌ Source and target positions are the same!")
            return
        
        # Convert to 0-based indexing
        from_idx = from_pos - 1
        to_idx = to_pos - 1
        
        # Get the song to move
        queue_list = list(music_queue.queue)
        song = queue_list[from_idx]
        
        # Remove from old position and insert at new position
        queue_list.pop(from_idx)
        queue_list.insert(to_idx, song)
        
        # Update the queue
        music_queue.queue = deque(queue_list)
        
        embed = discord.Embed(
            title="↕️ Song Moved",
            description=f"Moved **{song.source.title}** from position {from_pos} to {to_pos}",
            color=0x1DB954
        )
        embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='automesh')
    async def automesh(self, ctx):
        """Toggle automesh mode"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        # Toggle automesh mode
        old_mode = music_queue.automesh_mode
        music_queue.automesh_mode = not music_queue.automesh_mode
        
        if music_queue.automesh_mode:
            # Switching to automesh mode
            # Move existing queue songs to the user's automesh queue
            if len(music_queue.queue) > 0:
                user_id = ctx.author.id
                if user_id not in music_queue.automesh_queues:
                    music_queue.automesh_queues[user_id] = deque()
                
                # Move songs to user's automesh queue
                songs_moved = 0
                while music_queue.queue:
                    song = music_queue.queue.popleft()
                    music_queue.automesh_queues[song.requester.id] = music_queue.automesh_queues.get(song.requester.id, deque())
                    music_queue.automesh_queues[song.requester.id].append(song)
                    songs_moved += 1
                
                embed = discord.Embed(
                    title="🔀 Automesh Mode Enabled",
                    description=f"Switched to automesh mode and organized {songs_moved} songs by requester",
                    color=0x9B59B6
                )
            else:
                embed = discord.Embed(
                    title="🔀 Automesh Mode Enabled",
                    description="Songs will now be organized by user in separate queues",
                    color=0x9B59B6
                )
        else:
            # Switching to normal mode
            # Move all automesh songs to the regular queue
            if music_queue.automesh_queues:
                songs_moved = 0
                for user_queue in music_queue.automesh_queues.values():
                    while user_queue:
                        song = user_queue.popleft()
                        music_queue.queue.append(song)
                        songs_moved += 1
                
                music_queue.automesh_queues.clear()
                
                embed = discord.Embed(
                    title="📋 Normal Mode Enabled",
                    description=f"Switched to normal queue mode and merged {songs_moved} songs",
                    color=0x1DB954
                )
            else:
                embed = discord.Embed(
                    title="📋 Normal Mode Enabled",
                    description="Songs will now be played in a single queue",
                    color=0x1DB954
                )
        
        embed.add_field(
            name="How it works",
            value="🔀 **Automesh**: Each user has their own queue, played in round-robin\n📋 **Normal**: All songs in one shared queue",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle music control reactions on now playing messages"""
        # Ignore bot reactions
        if user.bot:
            return
        
        # Check if this is a now playing message
        message = reaction.message
        guild_id = message.guild.id if message.guild else None
        
        if not guild_id or guild_id not in self.now_playing_messages:
            return
        
        # Check if this is the current now playing message
        if self.now_playing_messages[guild_id] != message.id:
            return
        
        # Get music queue and voice client
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            return
        
        # Remove the user's reaction
        try:
            await reaction.remove(user)
        except:
            pass  # Ignore if we can't remove the reaction
        
        # Handle different emoji reactions
        emoji = str(reaction.emoji)
        
        try:
            if emoji == '⏮️':  # Previous
                await self.play_previous_song(guild_id)
                
            elif emoji == '🔄':  # Restart
                await self.restart_current_song(guild_id)
                
            elif emoji == '⏸️':  # Pause
                if voice_client.is_playing():
                    voice_client.pause()
                    music_queue.pause_time = time.time()
                    
            elif emoji == '▶️':  # Resume/Play
                if voice_client.is_paused():
                    voice_client.resume()
                    # Adjust song start time for the pause duration
                    if hasattr(music_queue, 'pause_time') and hasattr(music_queue, 'song_start_time'):
                        pause_duration = time.time() - music_queue.pause_time
                        music_queue.song_start_time += pause_duration
                        delattr(music_queue, 'pause_time')
                        
            elif emoji == '⏭️':  # Skip
                voice_client.stop()  # This will trigger play_next_song
                
            elif emoji == '🔀':  # Shuffle
                if music_queue.automesh_mode:
                    # Shuffle automesh queues
                    for user_id, user_queue in music_queue.automesh_queues.items():
                        if len(user_queue) > 1:
                            songs_list = list(user_queue)
                            random.shuffle(songs_list)
                            music_queue.automesh_queues[user_id] = deque(songs_list)
                else:
                    # Shuffle regular queue
                    if len(music_queue.queue) > 1:
                        songs_list = list(music_queue.queue)
                        random.shuffle(songs_list)
                        music_queue.queue = deque(songs_list)
                        
            elif emoji == '🔉':  # Volume down
                current_volume = music_queue.volume
                new_volume = max(0.0, current_volume - 0.1)  # Decrease by 10%
                music_queue.volume = new_volume
                if voice_client.source and hasattr(voice_client.source, 'volume'):
                    voice_client.source.volume = new_volume
                    
            elif emoji == '🔊':  # Volume up
                current_volume = music_queue.volume
                new_volume = min(1.0, current_volume + 0.1)  # Increase by 10%
                music_queue.volume = new_volume
                if voice_client.source and hasattr(voice_client.source, 'volume'):
                    voice_client.source.volume = new_volume
                    
        except Exception as e:
            logger.error(f"Error handling music control reaction {emoji}: {e}")

    # --- Song Rating System Integration ---
    @commands.hybrid_command(name='rate')
    @app_commands.describe(rating="Your rating for the current song (1-5)")
    @app_commands.choices(rating=[
        app_commands.Choice(name="1 Star", value=1),
        app_commands.Choice(name="2 Stars", value=2),
        app_commands.Choice(name="3 Stars", value=3),
        app_commands.Choice(name="4 Stars", value=4),
        app_commands.Choice(name="5 Stars", value=5)
    ])
    async def rate(self, ctx, rating: int):
        """Rate the currently playing song (1-5 stars)"""
        # Validate rating first
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                await ctx.send("❌ Invalid rating. Please provide a number from 1 to 5.")
                return
        except (ValueError, TypeError):
            await ctx.send("❌ Invalid rating. Please provide a number from 1 to 5.")
            return
            
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        music_queue = self.get_music_queue(guild_id)
        db = MusicEloDatabase()
        song = music_queue.current_song
        if not song:
            await ctx.send("❌ Nothing is currently playing!")
            return
            
        # Debug logging
        logger.info(f"Rating attempt - User: {user_id}, Guild: {guild_id}, Rating: {rating}")
        logger.info(f"Song source type: {type(song.source)}")
        logger.info(f"Song source attributes: {dir(song.source)}")
        
               
        
               
        # Add song to DB if not present
        url = getattr(song.source, 'webpage_url', None) or getattr(song.source, 'url', None)
        logger.info(f"Song URL: {url}")
        
        if not url:
            await ctx.send("❌ Cannot rate this song (missing URL)")
            return
        song_row = db.get_song_by_url(url)
        if not song_row:
            try:
                song_id = db.add_song(url, song.source.title, getattr(song.source, 'uploader', None), getattr(song.source, 'duration', None), getattr(song.source, 'thumbnail', None))
                if not song_id:
                    logger.error(f"Failed to add song to database: url={url}, title={song.source.title}")
                    await ctx.send("❌ Failed to save song to database. Please try again.")
                    return
            except Exception as e:
                logger.error(f"Exception when adding song: {e}")
                await ctx.send("❌ Database error while saving song. Please try again.")
                return
        else:
            song_id = song_row[0]
        
        # Validate song_id before rating
        if not song_id:
            logger.error(f"Invalid song_id: song_id={song_id}, url={url}")
            await ctx.send("❌ Invalid song ID. Please try again.")
            return
        # Add or update rating
        if not db.add_song_rating(song_id, user_id, guild_id, rating):
            await ctx.send("❌ Failed to save rating. Please try again.")
            return
        await ctx.send(f"⭐ You rated **{song.source.title}**: {rating}/5")

    @commands.hybrid_command(name='myratings')
    @app_commands.describe(page="Page number of your rating history")
    async def myratings(self, ctx, page: int = 1):
        """Show your personal song rating history (paginated)"""
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        db = MusicEloDatabase()
        per_page = 10
        offset = (page - 1) * per_page
        ratings = db.get_user_ratings(user_id, guild_id, limit=per_page, offset=offset)
        total = db.get_user_rating_count(user_id, guild_id)
        if not ratings:
            await ctx.send("You have not rated any songs yet.")
            return
        embed = discord.Embed(title=f"Your Song Ratings (Page {page})", color=0xFFD700)
        for title, artist, url, thumb, rating, rated_at in ratings:
            name = f"{title} - {artist}" if artist else title
            value = f"⭐ {rating}/5 | [Link]({url}) | {rated_at}"
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text=f"Showing {offset+1}-{min(offset+per_page, total)} of {total} ratings")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='toprated')
    @app_commands.describe(timeframe="day/week/month/all", limit="Number of songs to show (default 10)")
    async def toprated(self, ctx, timeframe: str = 'all', limit: int = 10):
        """Show the server's highest-rated songs"""
        guild_id = ctx.guild.id
        db = MusicEloDatabase()
        songs = db.get_top_rated_songs(guild_id, timeframe=timeframe, limit=limit)
        if not songs:
            await ctx.send("No rated songs found for this server.")
            return
        embed = discord.Embed(title=f"Top Rated Songs ({timeframe})", color=0xFFD700)
        for title, artist, url, thumb, avg_rating, total_ratings in songs:
            name = f"{title} - {artist}" if artist else title
            value = f"⭐ {avg_rating:.2f}/5 ({total_ratings} ratings) | [Link]({url})"
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ratingstats')
    async def ratingstats(self, ctx):
        """Show detailed rating statistics for the current song"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        db = MusicEloDatabase()
        song = music_queue.current_song
        if not song:
            await ctx.send("❌ Nothing is currently playing!")
            return
        url = getattr(song.source, 'webpage_url', None) or getattr(song.source, 'url', None)
        song_row = db.get_song_by_url(url)
        if not song_row:
            await ctx.send("No ratings for this song yet.")
            return
        song_id = song_row[0]
        stats = db.get_song_rating_stats(song_id, guild_id)
        embed = discord.Embed(title=f"Rating Stats: {song.source.title}", color=0xFFD700)
        embed.add_field(name="Average Rating", value=f"⭐ {stats['avg_rating']:.2f}/5", inline=True)
        embed.add_field(name="Total Ratings", value=str(stats['total_ratings']), inline=True)
        dist = stats['rating_distribution']
        dist_str = '\n'.join([f"{k}⭐: {v}" for k, v in sorted(dist.items(), reverse=True)])
        embed.add_field(name="Distribution", value=dist_str or "No ratings yet.", inline=False)
        # Recent ratings
        recent = db.get_recent_ratings(song_id, guild_id, limit=5)
        if recent:
            user_lines = []
            for rating, rated_at, uid in recent:
                user = self.bot.get_user(uid)
                user_str = user.mention if user else f"User {uid}"
                user_lines.append(f"{user_str}: ⭐ {rating}/5 at {rated_at}")
            embed.add_field(name="Recent Ratings", value='\n'.join(user_lines), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='recommend')
    @app_commands.describe(count="Number of recommendations (default 5)")
    async def recommend(self, ctx, count: int = 5):
        """Suggest songs based on your rating history and similar users' preferences"""
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        db = MusicEloDatabase()
        recs = db.get_user_recommendations(user_id, guild_id, limit=count)
        if not recs:
            await ctx.send("No recommendations found. Rate more songs for better suggestions!")
            return
        embed = discord.Embed(title="Recommended Songs For You", color=0x1DB954)
        for title, artist, avg_rating in recs:
            name = f"{title} - {artist}" if artist else title
            value = f"Average Rating: ⭐ { avg_rating:.2f}/5"
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='cached', aliases=['cache'])
    @app_commands.describe(page="Page number (default 1)", limit="Songs per page (default 10)")
    async def cached_songs(self, ctx, page: int = 1, limit: int = 10):
        """Show all cached songs (recently played and highly rated)"""
        guild_id = ctx.guild.id
        db = MusicEloDatabase()
        
        # Update cache first
        db.update_song_cache(guild_id)
        
        # Get total count for pagination
        all_cached = db.get_cached_songs(guild_id, limit=1000)  # Get all for counting
        total_songs = len(all_cached)
        
        if total_songs == 0:
            embed = discord.Embed(
                title="🗄️ Cached Songs",
                description="No songs are currently cached. Play some songs or rate them to build the cache!",
                color=0x1DB954
            )
            await ctx.send(embed=embed)
            return
        
        # Calculate pagination
        total_pages = (total_songs + limit - 1) // limit
        page = max(1, min(page, total_pages))
        
        offset = (page - 1) * limit
        cached_songs = all_cached[offset:offset + limit]
        
        embed = discord.Embed(
            title="🗄️ Cached Songs",
            description=f"Songs cached for quick access (Page {page}/{total_pages})",
            color=0x1DB954
        )
        
        # Group by cache reason
        recent_songs = []
        rated_songs = []
        
        for title, artist, url, cache_reason, cached_at, file_path, file_size in cached_songs:
            song_display = f"**{title}**" + (f" - {artist}" if artist else "")
            
            # Add file size info if available
            size_info = ""
            if file_path and file_size:
                if file_size > 1024 * 1024:  # MB
                    size_info = f" ({file_size / (1024 * 1024):.1f} MB)"
                else:  # KB
                    size_info = f" ({file_size / 1024:.1f} KB)"
            
            song_line = f"[{song_display}]({url}){size_info}"
            
            if cache_reason == 'recent_play':
                recent_songs.append(song_line)
            elif cache_reason == 'high_rating':
                rated_songs.append(song_line)
            elif cache_reason == 'downloaded':
                # Check if file still exists
                if file_path and os.path.exists(file_path):
                    rated_songs.append(song_line + " 📁")
                else:
                    rated_songs.append(song_line + " ❌")
        
        if recent_songs:
            embed.add_field(
                name="🕒 Recently Played (Last 30 Days)",
                value='\n'.join(recent_songs[:10]),  # Limit to prevent embed overflow
                inline=False
            )
        
        if rated_songs:
            embed.add_field(
                name="⭐ Highly Rated (Rating > 2.5)",
                value='\n'.join(rated_songs[:10]),  # Limit to prevent embed overflow
                inline=False
            )
        
        embed.set_footer(text=f"Total cached songs: {total_songs} | Use `/cached <page>` to see more")
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='playtoprated', aliases=['ptr'])
    @app_commands.describe(limit="Number of top rated songs to play (default 50, max 50)")
    async def play_top_rated(self, ctx, limit: int = 50):
        """Play the server's top-rated songs"""
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel to use this command!")
            return
        
        if limit < 1 or limit > 50:
            await ctx.send("❌ Limit must be between 1 and 50!")
            return
        
        guild_id = ctx.guild.id
        db = MusicEloDatabase()
        
        # Defer response for slash commands to prevent timeout
        if ctx.interaction:
            await ctx.defer()
        
        # Get top rated songs
        top_songs = db.get_top_rated_songs(guild_id, timeframe='all', limit=limit)
        
        if not top_songs:
            # Check if there are any songs at all in the database for this guild
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM songs s JOIN song_ratings sr ON s.id = sr.song_id WHERE sr.guild_id = ?", (guild_id,))
                rated_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(DISTINCT s.id) FROM songs s WHERE s.id IN (SELECT DISTINCT song_id FROM song_ratings WHERE guild_id = ?) OR s.url IN (SELECT DISTINCT s2.url FROM songs s2)", (guild_id,))
                total_songs = cursor.fetchone()[0]
            finally:
                conn.close()
            
            if total_songs > 0 and rated_count == 0:
                await ctx.send("🎵 This server has songs but none are rated yet!\n💡 Use `/rate 1-5` while a song is playing to start building your top-rated playlist!")
            elif total_songs > 0:
                await ctx.send(f"🎵 Found {total_songs} songs but none meet the rating criteria yet!\n💡 Songs need at least 1 rating to appear in top-rated. Use `/rate 1-5` while listening!")
            else:
                await ctx.send("🎵 No songs found for this server! Play some music first with `/play`, then rate them with `/rate 1-5`!")
            return
        
        voice_channel = ctx.author.voice.channel
        music_queue = self.get_music_queue(guild_id)
        
        # Store the channel for now playing messages
        self.last_music_channels[guild_id] = ctx.channel.id
        
        # Connect to voice channel if not already connected
        if guild_id not in self.voice_clients or not self.voice_clients[guild_id].is_connected():
            try:
                voice_client = await asyncio.wait_for(
                    voice_channel.connect(timeout=10.0, reconnect=True),
                    timeout=15.0
                )
                self.voice_clients[guild_id] = voice_client
                await ctx.send(f"🔗 Connected to **{voice_channel.name}**")
            except Exception as e:
                await ctx.send(f"❌ Failed to connect to voice channel: {str(e)}")
                return
        
        # Send initial message
        processing_msg = await ctx.send(f"🎵 Adding {len(top_songs)} top-rated songs to queue...")
        
        added_count = 0
        failed_count = 0
        
        for i, (title, artist, url, thumb, avg_rating, total_ratings) in enumerate(top_songs):
            try:
                # Update progress every 10 songs
                if i % 10 == 0 and i > 0:
                    await processing_msg.edit(content=f"🎵 Processing... {i}/{len(top_songs)} songs added")
                
                # Create audio source from URL
                source = await YTDLSource.create_source(ctx, url, loop=self.bot.loop)
                song = Song(source, ctx.author)
                music_queue.add_song(song)
                added_count += 1
                
            except Exception as e:
                logger.warning(f"Failed to add top-rated song {title}: {e}")
                failed_count += 1
                continue
        
        # Create summary embed
        embed = discord.Embed(
            title="🏆 Top-Rated Songs Added",
            description=f"Added {added_count} of the server's highest-rated songs to the queue",
            color=0xFFD700
        )
        embed.add_field(name="Successfully Added", value=str(added_count), inline=True)
        if failed_count > 0:
            embed.add_field(name="Failed to Add", value=str(failed_count), inline=True)
        embed.add_field(name="Queue Mode", value="Automesh" if music_queue.automesh_mode else "Normal", inline=True)
        
        # Show some sample songs
        if added_count > 0:
            sample_songs = top_songs[:3]  # Show first 3 songs
            sample_text = []
            for title, artist, url, thumb, avg_rating, total_ratings in sample_songs:
                name = f"{title} - {artist}" if artist else title
                sample_text.append(f"⭐ {avg_rating:.2f}/5 - {name}")
            embed.add_field(name="Top Songs Added", value='\n'.join(sample_text), inline=False)
        
        await processing_msg.edit(content="", embed=embed)
        
        # Start playing if nothing is currently playing
        if not music_queue.is_playing and added_count > 0:
            await self.play_next_song(guild_id, skip_now_playing_message=True)

    @commands.hybrid_command(name='streammode')
    @app_commands.describe(enable="Enable or disable continuous stream mode")
    async def stream_mode(self, ctx, enable: bool = None):
        """Toggle continuous stream mode for gapless playback"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        
        if enable is None:
            # Show current status
            current_status = getattr(music_queue, 'stream_mode', False)
            embed = discord.Embed(
                title="🎵 Continuous Stream Mode",
                description=f"Stream mode is currently **{'enabled' if current_status else 'disabled'}**",
                color=0x1DB954 if current_status else 0x95A5A6
            )
            embed.add_field(
                name="What is Stream Mode?",
                value="Creates a continuous audio stream with gapless transitions between songs",
                inline=False
            )
            embed.add_field(
                name="Benefits",
                value="• No gaps between songs\n• Smoother transitions\n• Better for playlists\n• Radio-style playback",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Toggle stream mode
        music_queue.stream_mode = enable
        
        embed = discord.Embed(
            title="🎵 Stream Mode Updated",
            description=f"Continuous stream mode **{'enabled' if enable else 'disabled'}**",
            color=0x00FF00 if enable else 0xFF6B6B
        )
        
        if enable:
            embed.add_field(
                name="Next Songs",
                value="Will play with gapless transitions",
                inline=True
            )
            embed.add_field(
                name="Cache Usage", 
                value="Will prefer cached files for best quality",
                inline=True
            )
        else:
            embed.add_field(
                name="Playback",
                value="Will return to normal song-by-song playback",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='createstream')
    @app_commands.describe(
        playlist_name="Name of playlist to stream",
        crossfade="Crossfade duration in seconds (0-10)",
        loop="Loop the playlist continuously"
    )
    async def create_stream(self, ctx, playlist_name: str, crossfade: float = 0.0, loop: bool = False):
        """Create a continuous MPEG stream from a playlist"""
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel to start a stream!")
            return
        
        # Validate crossfade
        if crossfade < 0 or crossfade > 10:
            await ctx.send("❌ Crossfade must be between 0 and 10 seconds!")
            return
        
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        db = MusicEloDatabase()
        
        # Defer response for processing
        if ctx.interaction:
            await ctx.defer()
        
        # Handle special "Top Rated" playlist
        if playlist_name.lower() in ["top rated", "toprated", "top-rated"]:
            songs = db.get_top_rated_songs_as_playlist(guild_id, limit=50)
            if not songs:
                await ctx.send("❌ No top-rated songs found!")
                return
        else:
            # Get user playlist
            playlist = db.get_playlist_by_name(user_id, guild_id, playlist_name)
            if not playlist:
                await ctx.send(f"❌ Playlist **{playlist_name}** not found!")
                return
            
            playlist_id = playlist[0]
            songs = db.get_playlist_songs(playlist_id, limit=50)
            if not songs:
                await ctx.send(f"❌ Playlist **{playlist_name}** is empty!")
                return
        
        # Send processing message
        processing_msg = await ctx.send(f"🎵 Creating continuous stream for **{playlist_name}**...")
        
        try:
            # Create the continuous stream
            stream_source = await self.create_continuous_stream(
                ctx, songs, crossfade=crossfade, loop=loop
            )
            
            if not stream_source:
                await processing_msg.edit(content="❌ Failed to create stream!")
                return
            
            # Connect to voice and start stream
            voice_channel = ctx.author.voice.channel
            music_queue = self.get_music_queue(guild_id)
            
            # Store the channel for now playing messages
            self.last_music_channels[guild_id] = ctx.channel.id
            
            # Connect to voice channel if not already connected
            if guild_id not in self.voice_clients or not self.voice_clients[guild_id].is_connected():
                try:
                    voice_client = await voice_channel.connect()
                    self.voice_clients[guild_id] = voice_client
                except Exception as e:
                    await processing_msg.edit(content=f"❌ Failed to connect to voice channel: {str(e)}")
                    return
            
            voice_client = self.voice_clients[guild_id]
            
            # Stop current playback
            if voice_client.is_playing():
                voice_client.stop()
            
            # Clear queue and set stream mode
            music_queue.clear()
            music_queue.stream_mode = True
            music_queue.current_stream_info = {
                'playlist_name': playlist_name,
                'song_count': len(songs),
                'crossfade': crossfade,
                'loop': loop
            }
            
            # Start the stream
            voice_client.play(stream_source, after=lambda e: self.bot.loop.create_task(
                self.handle_stream_end(guild_id, e)
            ))
            
            # Create success embed
            embed = discord.Embed(
                title="🎵 Continuous Stream Started",
                description=f"Now streaming **{playlist_name}** with {len(songs)} songs",
                color=0x9B59B6
            )
            
            embed.add_field(name="Playlist", value=playlist_name, inline=True)
            embed.add_field(name="Songs", value=str(len(songs)), inline=True)
            embed.add_field(name="Mode", value="Loop" if loop else "Once", inline=True)
            
            if crossfade > 0:
                embed.add_field(name="Crossfade", value=f"{crossfade}s", inline=True)
            
            embed.add_field(
                name="Controls",
                value="Use `/stop` to end stream\nUse `/streamstats` for stream info",
                inline=False
            )
            
            embed.set_footer(text=f"Stream started in {voice_channel.name}")
            
            await processing_msg.edit(content="", embed=embed)
            
            # Update bot status
            await self.update_bot_status()
            
        except Exception as e:
            logger.error(f"Error creating stream: {e}")
            await processing_msg.edit(content=f"❌ Failed to create stream: {str(e)}")

    async def create_continuous_stream(self, ctx, songs, crossfade=0.0, loop=False):
        """Create a continuous FFmpeg stream from a list of songs"""
        try:
            # Create temporary playlist file for FFmpeg
            playlist_file = f"temp_stream_playlist_{ctx.guild.id}_{int(time.time())}.txt"
            
            # Collect audio files (prefer cached, download if needed)
            audio_files = []
            for song_data in songs:
                if len(song_data) >= 4:  # Database format
                    url = song_data[3]  # URL is typically at index 3
                    title = song_data[1]  # Title at index 1
                else:  # Simple format
                    url = song_data.get('url', '')
                    title = song_data.get('title', 'Unknown')
                
                try:
                    # Try to get cached file first
                    source = await YTDLSource.create_source(
                        ctx, url, loop=self.bot.loop, download=True
                    )
                    
                    if hasattr(source, 'downloaded_file') and source.downloaded_file:
                        audio_files.append(source.downloaded_file)
                    else:
                        # Fallback to stream URL
                        audio_files.append(source.url)
                    
                except Exception as e:
                    logger.warning(f"Failed to get audio for {title}: {e}")
                    continue
            
            if not audio_files:
                logger.error("No audio files available for stream")
                return None
            
            # Create FFmpeg concat playlist
            with open(playlist_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    # Escape special characters for FFmpeg
                    escaped_path = audio_file.replace("'", r"\'").replace('"', r'\"')
                    f.write(f"file '{escaped_path}'\n")
                
                # Add loop directive if needed
                if loop:
                    f.write("# Loop the playlist\n")
                    for audio_file in audio_files:
                        escaped_path = audio_file.replace("'", r"\'").replace('"', r'\"')
                        f.write(f"file '{escaped_path}'\n")
            
            # Build FFmpeg command for continuous stream
            ffmpeg_options = {
                'before_options': '-re',  # Read input at native frame rate
                'options': f'-vn -acodec pcm_s16le -ar 48000 -ac 2 -f s16le'
            }
            
            # Add crossfade filter if specified
            if crossfade > 0:
                # This creates smooth transitions between tracks
                filter_complex = f'[0:a]volume=1.0[a0];'
                for i in range(1, len(audio_files)):
                    filter_complex += f'[{i}:a]volume=1.0[a{i}];'
                
                # Create crossfade chain
                for i in range(len(audio_files) - 1):
                    if i == 0:
                        filter_complex += f'[a0][a1]acrossfade=d={crossfade}[cf1];'
                    else:
                        filter_complex += f'[cf{i}][a{i+1}]acrossfade=d={crossfade}[cf{i+1}];'
                
                ffmpeg_options['options'] += f' -filter_complex "{filter_complex}" -map "[cf{len(audio_files)-1}]"'
            
            # Create the audio source
            stream_source = discord.FFmpegPCMAudio(
                f'concat:{"|".join(audio_files)}' if len(audio_files) > 1 else audio_files[0],
                **ffmpeg_options
            )
            
            # Clean up temporary playlist file
            try:
                os.remove(playlist_file)
            except:
                pass
            
            return stream_source
            
        except Exception as e:
            logger.error(f"Error creating continuous stream: {e}")
            return None

    async def handle_stream_end(self, guild_id, error):
        """Handle when a continuous stream ends"""
        if error:
            logger.error(f"Stream error in guild {guild_id}: {error}")
        
        music_queue = self.get_music_queue(guild_id)
        
        # Check if stream should loop
        if hasattr(music_queue, 'current_stream_info') and music_queue.current_stream_info.get('loop', False):
            # Restart the stream
            logger.info(f"Restarting looped stream in guild {guild_id}")
            # Implementation would go here to restart the stream
        else:
            # Clean up stream mode
            music_queue.stream_mode = False
            if hasattr(music_queue, 'current_stream_info'):
                delattr(music_queue, 'current_stream_info')
            
            # Send notification if we have a channel
            if guild_id in self.last_music_channels:
                try:
                    channel = self.bot.get_channel(self.last_music_channels[guild_id])
                    if channel:
                        embed = discord.Embed(
                            title="🎵 Stream Ended",
                            description="Continuous stream has finished playing",
                            color=0x95A5A6
                        )
                        await channel.send(embed=embed)
                except:
                    pass

    @commands.hybrid_command(name='streamstats')
    async def stream_stats(self, ctx):
        """Show current stream statistics"""
        guild_id = ctx.guild.id
        music_queue = self.get_music_queue(guild_id)
        voice_client = self.voice_clients.get(guild_id)
        
        if not hasattr(music_queue, 'stream_mode') or not music_queue.stream_mode:
            await ctx.send("❌ No active stream in this server!")
            return
        
        embed = discord.Embed(
            title="📊 Stream Statistics",
            color=0x9B59B6
        )
        
        # Stream status
        is_playing = voice_client and voice_client.is_playing()
        embed.add_field(
            name="Status",
            value="🔴 Live" if is_playing else "⏸️ Stopped",
            inline=True
        )
        
        # Stream info
        if hasattr(music_queue, 'current_stream_info'):
            info = music_queue.current_stream_info
            embed.add_field(name="Playlist", value=info.get('playlist_name', 'Unknown'), inline=True)
            embed.add_field(name="Songs", value=str(info.get('song_count', 0)), inline=True)
            
            if info.get('crossfade', 0) > 0:
                embed.add_field(name="Crossfade", value=f"{info['crossfade']}s", inline=True)
            
            embed.add_field(
                name="Loop Mode",
                value="✅ Enabled" if info.get('loop', False) else "❌ Disabled",
                inline=True
            )
        
        # Voice channel info
        if voice_client and voice_client.channel:
            embed.add_field(
                name="Voice Channel",
                value=voice_client.channel.name,
                inline=True
            )
            
            # Count listeners
            listeners = len([m for m in voice_client.channel.members if not m.bot])
            embed.add_field(name="Listeners", value=str(listeners), inline=True)
        
        embed.set_footer(text="Use /stop to end the stream")
        await ctx.send(embed=embed)


async def setup(bot):
    """Setup function to load the Music cog"""
    await bot.add_cog(Music(bot))
