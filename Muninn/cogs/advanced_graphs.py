import discord
from discord.ext import commands
from discord.ui import View, Button
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import sqlite3
import os
import io
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np
import pytz
from cogs.graphs.discord_theme import DiscordTheme
import unicodedata

def convert_to_california_time(timestamp: datetime) -> datetime:
    """Convert timestamp to California timezone."""
    if timestamp is None:
        raise ValueError("Timestamp cannot be None.")
    if timestamp.tzinfo is None:
        timestamp = pytz.utc.localize(timestamp)
    california_zone = pytz.timezone('America/Los_Angeles')
    california_time = timestamp.astimezone(california_zone)
    return california_time


def sanitize_text(s: object) -> str:
    """Return an ASCII-only sanitized string safe for matplotlib rendering.

    Many servers generating images are headless and may not have fonts for
    a user's full Unicode name (emoji, CJK, combining marks). To avoid missing
    glyph boxes in saved images we normalize to NFKD, strip format chars and
    then drop any non-ASCII bytes.
    """
    if s is None:
        return ""
    text = str(s)
    # Normalize and decompose characters (separates accents)
    text = unicodedata.normalize('NFKD', text)

    # Remove control/format characters (category C*), like ZWJ/VS
    filtered = [ch for ch in text if not unicodedata.category(ch).startswith('C')]
    text = ''.join(filtered)

    # Encode to ASCII, dropping characters that can't be represented
    try:
        ascii_text = text.encode('ascii', 'ignore').decode('ascii')
    except Exception:
        # Fallback conservative removal
        ascii_text = ''.join(ch for ch in text if ord(ch) < 128)

    # Collapse whitespace and return
    return ' '.join(ascii_text.split()).strip()

class GraphSelector(View):
    """Interactive UI for selecting different graph types."""
    
    def __init__(self, cog, ctx, user):
        super().__init__(timeout=180)  # 3 minute timeout
        self.cog = cog
        self.ctx = ctx
        self.user = user
        self.message = None
        
    async def on_timeout(self):
        """Disable all buttons when view times out."""
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)
    
    @discord.ui.button(label="📊 Activity Heatmap", style=discord.ButtonStyle.primary, custom_id="heatmap")
    async def heatmap_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_activity_heatmap(self.ctx, self.user)
        
    @discord.ui.button(label="📈 Message Trends", style=discord.ButtonStyle.primary, custom_id="trends")
    async def trends_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_message_trends(self.ctx, self.user)
        
    @discord.ui.button(label="🎯 Engagement Stats", style=discord.ButtonStyle.primary, custom_id="engagement")
    async def engagement_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_engagement_stats(self.ctx, self.user)
        
    @discord.ui.button(label="📅 Weekly Activity", style=discord.ButtonStyle.primary, custom_id="weekly")
    async def weekly_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_weekly_activity(self.ctx, self.user)
        
    @discord.ui.button(label="💬 Message Distribution", style=discord.ButtonStyle.primary, custom_id="distribution")
    async def distribution_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_message_distribution(self.ctx, self.user)
        
    @discord.ui.button(label="⏰ Hourly Pattern", style=discord.ButtonStyle.success, custom_id="hourly")
    async def hourly_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_hourly_pattern(self.ctx, self.user)
        
    @discord.ui.button(label="🆚 Compare Users", style=discord.ButtonStyle.success, custom_id="compare")
    async def compare_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_user_comparison(self.ctx)
        
    @discord.ui.button(label="📝 Word Cloud", style=discord.ButtonStyle.success, custom_id="wordcloud")
    async def wordcloud_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_word_analysis(self.ctx, self.user)
        
    @discord.ui.button(label="🎨 Channel Overview", style=discord.ButtonStyle.success, custom_id="channels")
    async def channels_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.cog.generate_channel_overview(self.ctx, self.user)
        
    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.delete()
        self.stop()


class AdvancedGraphs(commands.Cog):
    """Advanced statistics visualization with interactive UI."""
    
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')
        
    def get_db_connection(self):
        """Create and return a database connection."""
        return sqlite3.connect("discord.db")
    
    async def generate_activity_heatmap(self, ctx, user):
        """Generate a heatmap showing activity by hour and day of week."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get all messages from the user
            cursor.execute("""
                SELECT timestamp FROM user_activity 
                WHERE user_id = ? AND guild_id = ?
            """, (user.id, ctx.guild.id))
            
            timestamps = cursor.fetchall()
            
            if not timestamps:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            # Create a 7x24 grid (days x hours)
            heatmap_data = np.zeros((7, 24))
            
            for (ts,) in timestamps:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts)
                    else:
                        dt = ts
                    
                    dt = convert_to_california_time(dt)
                    day = dt.weekday()  # 0=Monday, 6=Sunday
                    hour = dt.hour
                    heatmap_data[day][hour] += 1
                except Exception as e:
                    continue
            
            # Create heatmap
            fig, ax = plt.subplots(figsize=(14, 6))
            
            # Create color map - use Discord colors
            colors = ['#2C2F33', '#5762E3', '#57F287']
            n_bins = 100
            cmap = sns.blend_palette(colors, n_colors=n_bins, as_cmap=True)
            
            sns.heatmap(heatmap_data, 
                       cmap=cmap,
                       cbar_kws={'label': 'Message Count'},
                       linewidths=0.5,
                       linecolor='#99AAB5',
                       ax=ax)
            
            # Sanitize user display name and other labels to avoid unsupported glyphs
            title_text = sanitize_text(f"Activity Heatmap - {user.display_name}")
            ax.set_title(title_text, fontproperties=prop, fontsize=16, pad=20)
            ax.set_xlabel(sanitize_text("Hour of Day"), fontproperties=prop, fontsize=12)
            ax.set_ylabel(sanitize_text("Day of Week"), fontproperties=prop, fontsize=12)

            # Set labels and ensure tick labels use the provided font property
            y_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            ax.set_yticks(np.arange(len(y_labels)) + 0.5)
            ax.set_yticklabels([sanitize_text(l) for l in y_labels], rotation=0, fontproperties=prop)

            x_labels = [str(h) for h in range(24)]
            ax.set_xticks(np.arange(len(x_labels)) + 0.5)
            ax.set_xticklabels([sanitize_text(l) for l in x_labels], fontproperties=prop)

            # Ensure colorbar label uses our font and sanitized text
            cbar = ax.collections[0].colorbar
            if cbar is not None:
                cbar.set_label(sanitize_text('Message Count'), fontproperties=prop)
                for t in cbar.ax.get_yticklabels():
                    t.set_fontproperties(prop)
            
            plt.tight_layout()
            
            # Save and send
            file_path = f"cogs/graphs/temp_heatmap_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating heatmap: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_message_trends(self, ctx, user):
        """Generate a time series graph showing message trends over time."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get messages from the past 30 days
            start_date = datetime.utcnow() - timedelta(days=30)
            california_start = convert_to_california_time(start_date)
            
            cursor.execute("""
                SELECT DATE(timestamp), COUNT(*), AVG(message_length), AVG(word_count)
                FROM user_activity
                WHERE user_id = ? AND guild_id = ? AND timestamp >= ?
                GROUP BY DATE(timestamp)
                ORDER BY DATE(timestamp)
            """, (user.id, ctx.guild.id, california_start.strftime('%Y-%m-%d')))
            
            data = cursor.fetchall()
            
            if not data:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            dates = [datetime.strptime(row[0], '%Y-%m-%d') for row in data]
            message_counts = [row[1] for row in data]
            avg_lengths = [row[2] for row in data]
            avg_words = [row[3] for row in data]
            
            # Create figure with subplots
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))
            
            # Message count trend
            ax1.plot(dates, message_counts, color='#5762E3', linewidth=2, marker='o')
            ax1.fill_between(dates, message_counts, alpha=0.3, color='#5762E3')
            ax1.set_title(sanitize_text(f"Message Trends - {user.display_name}"), 
                         fontproperties=prop, fontsize=16)
            ax1.set_ylabel("Messages Sent", fontproperties=prop)
            ax1.grid(True, alpha=0.3)
            
            # Average message length trend
            ax2.plot(dates, avg_lengths, color='#57F287', linewidth=2, marker='s')
            ax2.fill_between(dates, avg_lengths, alpha=0.3, color='#57F287')
            ax2.set_ylabel("Avg Message Length", fontproperties=prop)
            ax2.grid(True, alpha=0.3)
            
            # Average words per message trend
            ax3.plot(dates, avg_words, color='#FEE75C', linewidth=2, marker='^')
            ax3.fill_between(dates, avg_words, alpha=0.3, color='#FEE75C')
            ax3.set_ylabel("Avg Words/Message", fontproperties=prop)
            ax3.set_xlabel("Date", fontproperties=prop)
            ax3.grid(True, alpha=0.3)
            
            # Format x-axis
            for ax in [ax1, ax2, ax3]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                ax.tick_params(axis='x', rotation=45)
            
            plt.tight_layout()
            
            file_path = f"cogs/graphs/temp_trends_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating trends: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_engagement_stats(self, ctx, user):
        """Generate engagement statistics including emojis, media, mentions."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT emoji_count, has_media, attachment_count, 
                       mentioned_users, mentioned_roles
                FROM user_activity
                WHERE user_id = ? AND guild_id = ?
            """, (user.id, ctx.guild.id))
            
            data = cursor.fetchall()
            
            if not data:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            total_messages = len(data)
            total_emojis = sum(row[0] for row in data if row[0])
            messages_with_media = sum(1 for row in data if row[1])
            total_attachments = sum(row[2] for row in data if row[2])
            messages_with_mentions = sum(1 for row in data if row[3])
            messages_with_role_mentions = sum(1 for row in data if row[4])
            
            # Create pie charts and bar charts
            fig = plt.figure(figsize=(14, 8))
            gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
            
            # Media usage pie chart
            ax1 = fig.add_subplot(gs[0, 0])
            media_data = [messages_with_media, total_messages - messages_with_media]
            colors1 = ['#5762E3', '#2C2F33']
            ax1.pie(media_data, labels=['With Media', 'Text Only'], 
                   autopct='%1.1f%%', colors=colors1, startangle=90)
            ax1.set_title("Media Usage", fontproperties=prop, fontsize=14)
            
            # Mention usage pie chart
            ax2 = fig.add_subplot(gs[0, 1])
            mention_data = [messages_with_mentions, total_messages - messages_with_mentions]
            colors2 = ['#57F287', '#2C2F33']
            ax2.pie(mention_data, labels=['With Mentions', 'No Mentions'],
                   autopct='%1.1f%%', colors=colors2, startangle=90)
            ax2.set_title("User Mentions", fontproperties=prop, fontsize=14)
            
            # Engagement metrics bar chart
            ax3 = fig.add_subplot(gs[1, :])
            metrics = ['Avg Emojis/Msg', 'Media %', 'Mention %', 'Attachments/Msg']
            values = [
                total_emojis / total_messages if total_messages > 0 else 0,
                (messages_with_media / total_messages * 100) if total_messages > 0 else 0,
                (messages_with_mentions / total_messages * 100) if total_messages > 0 else 0,
                total_attachments / total_messages if total_messages > 0 else 0
            ]
            
            bars = ax3.bar(metrics, values, color=['#FEE75C', '#5762E3', '#57F287', '#EB459E'])
            ax3.set_title(sanitize_text(f"Engagement Metrics - {user.display_name}"), 
                         fontproperties=prop, fontsize=16)
            ax3.set_ylabel("Value", fontproperties=prop)
            ax3.grid(True, axis='y', alpha=0.3)
            
            # Add value labels on bars
            for bar, value in zip(bars, values):
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2., height,
                        f'{value:.2f}', ha='center', va='bottom', fontsize=10)
            
            plt.suptitle(sanitize_text(f"Total Messages: {total_messages}"), 
                        fontproperties=prop, fontsize=12, y=0.98)
            
            file_path = f"cogs/graphs/temp_engagement_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating engagement stats: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_weekly_activity(self, ctx, user):
        """Generate weekly activity comparison."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get last 8 weeks of data
            start_date = datetime.utcnow() - timedelta(weeks=8)
            california_start = convert_to_california_time(start_date)
            
            cursor.execute("""
                SELECT timestamp FROM user_activity
                WHERE user_id = ? AND guild_id = ? AND timestamp >= ?
            """, (user.id, ctx.guild.id, california_start.strftime('%Y-%m-%d')))
            
            timestamps = cursor.fetchall()
            
            if not timestamps:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            # Group by week
            week_counts = defaultdict(int)
            for (ts,) in timestamps:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts)
                    else:
                        dt = ts
                    dt = convert_to_california_time(dt)
                    week_start = dt - timedelta(days=dt.weekday())
                    week_key = week_start.strftime('%Y-%m-%d')
                    week_counts[week_key] += 1
                except:
                    continue
            
            # Sort by week
            sorted_weeks = sorted(week_counts.items())
            weeks = [datetime.strptime(w[0], '%Y-%m-%d').strftime('%m/%d') for w in sorted_weeks]
            counts = [w[1] for w in sorted_weeks]
            
            # Create bar chart
            fig, ax = plt.subplots(figsize=(12, 6))
            bars = ax.bar(weeks, counts, color='#5762E3', edgecolor='#99AAB5', linewidth=1.5)
            
            # Highlight highest week
            if counts:
                max_idx = counts.index(max(counts))
                bars[max_idx].set_color('#57F287')
            
            ax.set_title(sanitize_text(f"Weekly Activity - {user.display_name}"), 
                        fontproperties=prop, fontsize=16)
            ax.set_xlabel("Week Starting", fontproperties=prop)
            ax.set_ylabel("Messages Sent", fontproperties=prop)
            ax.grid(True, axis='y', alpha=0.3)
            plt.xticks(rotation=45)
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}', ha='center', va='bottom', fontsize=9)
            
            plt.tight_layout()
            
            file_path = f"cogs/graphs/temp_weekly_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating weekly activity: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_message_distribution(self, ctx, user):
        """Generate distribution analysis of message characteristics."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT message_length, word_count, emoji_count
                FROM user_activity
                WHERE user_id = ? AND guild_id = ?
            """, (user.id, ctx.guild.id))
            
            data = cursor.fetchall()
            
            if not data:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            lengths = [row[0] for row in data if row[0]]
            words = [row[1] for row in data if row[1]]
            emojis = [row[2] for row in data if row[2]]
            
            # Create histograms
            fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 5))
            
            # Message length distribution
            ax1.hist(lengths, bins=30, color='#5762E3', alpha=0.7, edgecolor='#99AAB5')
            ax1.axvline(np.mean(lengths), color='#ED4245', linestyle='--', 
                       linewidth=2, label=f'Mean: {np.mean(lengths):.1f}')
            ax1.set_title("Message Length", fontproperties=prop, fontsize=14)
            ax1.set_xlabel("Characters", fontproperties=prop)
            ax1.set_ylabel("Frequency", fontproperties=prop)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Word count distribution
            ax2.hist(words, bins=30, color='#57F287', alpha=0.7, edgecolor='#99AAB5')
            ax2.axvline(np.mean(words), color='#ED4245', linestyle='--',
                       linewidth=2, label=f'Mean: {np.mean(words):.1f}')
            ax2.set_title("Word Count", fontproperties=prop, fontsize=14)
            ax2.set_xlabel("Words", fontproperties=prop)
            ax2.set_ylabel("Frequency", fontproperties=prop)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # Emoji count distribution
            if emojis:
                ax3.hist(emojis, bins=20, color='#FEE75C', alpha=0.7, edgecolor='#99AAB5')
                ax3.axvline(np.mean(emojis), color='#ED4245', linestyle='--',
                           linewidth=2, label=f'Mean: {np.mean(emojis):.1f}')
            ax3.set_title("Emoji Count", fontproperties=prop, fontsize=14)
            ax3.set_xlabel("Emojis", fontproperties=prop)
            ax3.set_ylabel("Frequency", fontproperties=prop)
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            
            plt.suptitle(sanitize_text(f"Message Distribution - {user.display_name}"), 
                        fontproperties=prop, fontsize=16, y=1.02)
            plt.tight_layout()
            
            file_path = f"cogs/graphs/temp_distribution_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating distribution: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_hourly_pattern(self, ctx, user):
        """Generate 24-hour activity pattern."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT timestamp FROM user_activity
                WHERE user_id = ? AND guild_id = ?
            """, (user.id, ctx.guild.id))
            
            timestamps = cursor.fetchall()
            
            if not timestamps:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            # Count messages by hour
            hour_counts = [0] * 24
            for (ts,) in timestamps:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts)
                    else:
                        dt = ts
                    dt = convert_to_california_time(dt)
                    hour_counts[dt.hour] += 1
                except:
                    continue
            
            # Create polar plot
            fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
            
            # Convert hours to radians
            theta = np.linspace(0, 2 * np.pi, 24, endpoint=False)
            width = 2 * np.pi / 24
            
            # Create bars
            bars = ax.bar(theta, hour_counts, width=width, bottom=0, 
                         color='#5762E3', alpha=0.8, edgecolor='#99AAB5', linewidth=1.5)
            
            # Highlight peak hour
            if hour_counts:
                peak_hour = hour_counts.index(max(hour_counts))
                bars[peak_hour].set_color('#57F287')
            
            # Set labels
            ax.set_theta_zero_location('N')
            ax.set_theta_direction(-1)
            ax.set_xticks(theta)
            ax.set_xticklabels([f'{h:02d}:00' for h in range(24)])
            ax.set_ylim(0, max(hour_counts) * 1.1 if hour_counts else 1)
            
            ax.set_title(sanitize_text(f"24-Hour Activity Pattern - {user.display_name}\n" +
                        f"Peak Hour: {peak_hour:02d}:00 ({max(hour_counts)} messages)"),
                        fontproperties=prop, fontsize=16, pad=20)
            
            ax.grid(True, alpha=0.3)
            
            file_path = f"cogs/graphs/temp_hourly_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating hourly pattern: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_user_comparison(self, ctx):
        """Compare top users in the server."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT user_id, COUNT(*) as msg_count, 
                       AVG(message_length) as avg_len,
                       AVG(word_count) as avg_words,
                       AVG(emoji_count) as avg_emojis
                FROM user_activity
                WHERE guild_id = ?
                GROUP BY user_id
                ORDER BY msg_count DESC
                LIMIT 10
            """, (ctx.guild.id,))
            
            data = cursor.fetchall()
            
            if not data:
                await ctx.send("No data found for this server")
                return
            
            # Get user names (sanitize to avoid unsupported glyphs)
            user_names = []
            for row in data:
                try:
                    user = await self.bot.fetch_user(row[0])
                    raw_name = user.display_name if user else f"User {row[0]}"
                except:
                    raw_name = f"User {row[0]}"
                user_names.append(sanitize_text(raw_name))
            
            msg_counts = [row[1] for row in data]
            avg_lens = [row[2] for row in data]
            avg_words = [row[3] for row in data]
            avg_emojis = [row[4] for row in data]
            
            # Create comparison charts
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
            
            # Message count comparison
            bars1 = ax1.barh(user_names, msg_counts, color='#5762E3', edgecolor='#99AAB5')
            ax1.set_title("Total Messages", fontproperties=prop, fontsize=14)
            ax1.set_xlabel("Message Count", fontproperties=prop)
            ax1.grid(True, axis='x', alpha=0.3)
            
            # Average message length
            bars2 = ax2.barh(user_names, avg_lens, color='#57F287', edgecolor='#99AAB5')
            ax2.set_title("Avg Message Length", fontproperties=prop, fontsize=14)
            ax2.set_xlabel("Characters", fontproperties=prop)
            ax2.grid(True, axis='x', alpha=0.3)
            
            # Average words per message
            bars3 = ax3.barh(user_names, avg_words, color='#FEE75C', edgecolor='#99AAB5')
            ax3.set_title("Avg Words/Message", fontproperties=prop, fontsize=14)
            ax3.set_xlabel("Words", fontproperties=prop)
            ax3.grid(True, axis='x', alpha=0.3)
            
            # Average emojis per message
            bars4 = ax4.barh(user_names, avg_emojis, color='#EB459E', edgecolor='#99AAB5')
            ax4.set_title("Avg Emojis/Message", fontproperties=prop, fontsize=14)
            ax4.set_xlabel("Emojis", fontproperties=prop)
            ax4.grid(True, axis='x', alpha=0.3)
            
            plt.suptitle(sanitize_text(f"Top 10 Users Comparison - {ctx.guild.name}"), 
                        fontproperties=prop, fontsize=18, y=0.995)
            plt.tight_layout()
            
            file_path = f"cogs/graphs/temp_comparison_{ctx.guild.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating comparison: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_word_analysis(self, ctx, user):
        """Generate word usage analysis."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT message_length, word_count
                FROM user_activity
                WHERE user_id = ? AND guild_id = ?
            """, (user.id, ctx.guild.id))
            
            data = cursor.fetchall()
            
            if not data:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            # Calculate letters per word
            letters_per_word = []
            for msg_len, word_count in data:
                if word_count and word_count > 0:
                    letters_per_word.append(msg_len / word_count)
            
            if not letters_per_word:
                await ctx.send("Not enough data for word analysis")
                return
            
            # Create figure
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            
            # Distribution of letters per word
            ax1.hist(letters_per_word, bins=30, color='#5762E3', alpha=0.7, 
                    edgecolor='#99AAB5')
            mean_lpw = np.mean(letters_per_word)
            ax1.axvline(mean_lpw, color='#ED4245', linestyle='--', linewidth=2,
                       label=f'Mean: {mean_lpw:.2f}')
            ax1.set_title("Letters per Word Distribution", fontproperties=prop, fontsize=14)
            ax1.set_xlabel("Letters/Word", fontproperties=prop)
            ax1.set_ylabel("Frequency", fontproperties=prop)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Box plot
            box = ax2.boxplot([letters_per_word], vert=True, patch_artist=True,
                             labels=['Letters/Word'])
            for patch in box['boxes']:
                patch.set_facecolor('#5762E3')
                patch.set_alpha(0.7)
            for whisker in box['whiskers']:
                whisker.set_color('#99AAB5')
            for cap in box['caps']:
                cap.set_color('#99AAB5')
            for median in box['medians']:
                median.set_color('#ED4245')
                median.set_linewidth(2)
            
            ax2.set_title("Statistical Summary", fontproperties=prop, fontsize=14)
            ax2.set_ylabel("Letters/Word", fontproperties=prop)
            ax2.grid(True, axis='y', alpha=0.3)
            
            # Add statistics text
            stats_text = (f"Mean: {mean_lpw:.2f}\n"
                         f"Median: {np.median(letters_per_word):.2f}\n"
                         f"Std Dev: {np.std(letters_per_word):.2f}")
            ax2.text(1.15, np.median(letters_per_word), stats_text,
                    bbox=dict(boxstyle='round', facecolor='#2C2F33', alpha=0.8),
                    fontsize=10, verticalalignment='center')
            
            plt.suptitle(sanitize_text(f"Word Analysis - {user.display_name}"), 
                        fontproperties=prop, fontsize=16, y=0.98)
            plt.tight_layout()
            
            file_path = f"cogs/graphs/temp_words_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating word analysis: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    async def generate_channel_overview(self, ctx, user):
        """Generate per-channel activity overview for a user."""
        prop = DiscordTheme.apply_discord_theme()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT channel_id, COUNT(*) as msg_count
                FROM user_activity
                WHERE user_id = ? AND guild_id = ?
                GROUP BY channel_id
                ORDER BY msg_count DESC
                LIMIT 15
            """, (user.id, ctx.guild.id))
            
            data = cursor.fetchall()
            
            if not data:
                await ctx.send(f"No data found for {user.display_name}")
                return
            
            # Get channel names
            channel_names = []
            msg_counts = []
            for channel_id, count in data:
                try:
                    channel = ctx.guild.get_channel(channel_id)
                    # If not found in cache, try to fetch from API (may be a thread or archived)
                    if channel is None:
                        try:
                            channel = await self.bot.fetch_channel(channel_id)
                        except Exception:
                            channel = None

                    # Determine a readable name; handle threads specially
                    if channel is None:
                        readable = f"Channel {channel_id}"
                    else:
                        # discord.Thread is a subclass of abc.GuildChannel in newer discord.py
                        try:
                            # If it's a thread, include parent channel for context
                            if getattr(channel, 'parent', None) is not None and channel.type.name.startswith('public_thread') or channel.type.name.startswith('private_thread'):
                                parent_name = channel.parent.name if channel.parent else None
                                if parent_name:
                                    readable = f"#{parent_name}/{channel.name} (thread)"
                                else:
                                    readable = f"{channel.name} (thread)"
                            else:
                                # regular channel
                                readable = f"#{channel.name}"
                        except Exception:
                            # Fallback if channel type or attributes differ
                            readable = getattr(channel, 'name', f"Channel {channel_id}")

                    channel_names.append(sanitize_text(readable))
                    msg_counts.append(count)
                except Exception:
                    channel_names.append(sanitize_text(f"Channel {channel_id}"))
                    msg_counts.append(count)
            
            # Create pie chart and bar chart
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
            
            # Pie chart for top channels
            colors = plt.cm.twilight(np.linspace(0, 1, len(channel_names)))
            ax1.pie(msg_counts, labels=channel_names, autopct='%1.1f%%',
                   colors=colors, startangle=90)
            ax1.set_title("Channel Distribution", fontproperties=prop, fontsize=14)
            
            # Bar chart
            bars = ax2.barh(channel_names, msg_counts, color=colors, edgecolor='#99AAB5')
            ax2.set_title("Messages per Channel", fontproperties=prop, fontsize=14)
            ax2.set_xlabel("Message Count", fontproperties=prop)
            ax2.grid(True, axis='x', alpha=0.3)
            
            # Add value labels
            for bar, count in zip(bars, msg_counts):
                width = bar.get_width()
                ax2.text(width, bar.get_y() + bar.get_height()/2.,
                        f'{int(count)}', ha='left', va='center', fontsize=9,
                        bbox=dict(boxstyle='round', facecolor='#2C2F33', alpha=0.8))
            
            plt.suptitle(sanitize_text(f"Channel Overview - {user.display_name}"), 
                        fontproperties=prop, fontsize=16, y=0.98)
            plt.tight_layout()
            
            file_path = f"cogs/graphs/temp_channels_{user.id}.png"
            plt.savefig(file_path, bbox_inches="tight", dpi=150)
            plt.close()
            
            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)
            
        except Exception as e:
            await ctx.send(f"Error generating channel overview: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    @commands.command(name='graphs_menu', aliases=['viz', 'visualize'])
    async def show_graph_menu(self, ctx, user: str = None):
        """Display interactive graph selection menu."""
        
        # Determine user
        if user is None:
            target_user = ctx.author
        else:
            target_user = await self.search.find_user(user, ctx.guild)
            if not target_user:
                await ctx.send("User not found.")
                return
        
        # Create embed
        embed = discord.Embed(
            title="Advanced Statistics Dashboard",
            description=sanitize_text(f"Select a visualization for **{target_user.display_name}**\n\n") + (
                       "- Activity Heatmap - Hour x Day activity pattern\n"
                       "- Message Trends - 30-day message trends\n"
                       "- Engagement Stats - Emojis, media, mentions\n"
                       "- Weekly Activity - Last 8 weeks comparison\n"
                       "- Message Distribution - Length, words, emojis\n"
                       "- Hourly Pattern - 24-hour polar chart\n"
                       "- Compare Users - Top 10 server comparison\n"
                       "- Word Analysis - Letters per word analysis\n"
                       "- Channel Overview - Per-channel breakdown\n"
            ),
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else None)
        embed.set_footer(text="Click a button to generate a graph • Timeout: 3 minutes")
        
        # Create view
        view = GraphSelector(self, ctx, target_user)
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(AdvancedGraphs(bot))
