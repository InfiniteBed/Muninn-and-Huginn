import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import datetime
from typing import Optional

class SuggestionSystem(commands.Cog):
    """Handles user suggestions and approval system."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self._initialize_database()
        
    def _initialize_database(self):
        """Initialize the suggestions database table."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS suggestions (
                    suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    suggestion_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at DATETIME,
                    reviewed_by INTEGER,
                    review_notes TEXT
                )
            """)
            conn.commit()

    @app_commands.command(name="suggest_response", description="Suggest a new @ response")
    @app_commands.describe(response="The @ response to suggest")
    async def suggest_at_response(self, interaction: discord.Interaction, response: str):
        """Allow users to suggest new @ responses."""
        
        # Check if response is reasonable length
        if len(response) > 500:
            await interaction.response.send_message("❌ Suggestion too long (max 500 characters)", ephemeral=True)
            return
            
        if len(response.strip()) < 3:
            await interaction.response.send_message("❌ Suggestion too short (min 3 characters)", ephemeral=True)
            return
        
        # Store suggestion in database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO suggestions (guild_id, user_id, suggestion_type, content)
                VALUES (?, ?, ?, ?)
            """, (interaction.guild_id, interaction.user.id, "at_response", response.strip()))
            suggestion_id = cursor.lastrowid
            conn.commit()
        
        # Create embed for the suggestion
        embed = discord.Embed(
            title="New @ Response Suggestion",
            description=f"```{response}```",
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Suggested by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Suggestion ID", value=str(suggestion_id), inline=True)
        embed.add_field(name="Guild", value=interaction.guild.name, inline=True)
        
        # Send to user
        await interaction.response.send_message(
            f"✅ Your @ response suggestion has been submitted (ID: {suggestion_id})\n"
            f"It will be reviewed by moderators.",
            ephemeral=True
        )
        
        # Notify bot owner
        try:
            owner = await self.bot.fetch_user(867261583871836161)  # Bot owner ID
            if owner:
                await owner.send(embed=embed)
        except:
            pass

    @commands.group(name="suggestions", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def suggestions_group(self, ctx):
        """Suggestion management commands."""
        if ctx.invoked_subcommand is None:
            await self.list_pending_suggestions(ctx)

    @suggestions_group.command(name="list")
    @commands.has_permissions(administrator=True)
    async def list_suggestions(self, ctx, status: str = "pending"):
        """List suggestions by status."""
        await self.list_suggestions_by_status(ctx, status)

    @suggestions_group.command(name="pending")
    @commands.has_permissions(administrator=True)
    async def list_pending_suggestions(self, ctx):
        """List pending suggestions."""
        await self.list_suggestions_by_status(ctx, "pending")

    async def list_suggestions_by_status(self, ctx, status: str):
        """List suggestions with a specific status."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT suggestion_id, user_id, suggestion_type, content, created_at
                FROM suggestions 
                WHERE guild_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (ctx.guild.id, status))
            
            suggestions = cursor.fetchall()
        
        if not suggestions:
            await ctx.send(f"No {status} suggestions found.")
            return
        
        embed = discord.Embed(
            title=f"{status.title()} Suggestions",
            color=discord.Color.blue()
        )
        
        for suggestion_id, user_id, suggestion_type, content, created_at in suggestions:
            user = self.bot.get_user(user_id)
            user_name = user.display_name if user else f"User {user_id}"
            
            embed.add_field(
                name=f"ID {suggestion_id} - {suggestion_type}",
                value=f"**By:** {user_name}\n**Content:** {content[:100]}{'...' if len(content) > 100 else ''}\n**Date:** {created_at}",
                inline=False
            )
        
        embed.set_footer(text="Use !suggestions approve <id> or !suggestions reject <id>")
        await ctx.send(embed=embed)

    @suggestions_group.command(name="approve")
    @commands.has_permissions(administrator=True)
    async def approve_suggestion(self, ctx, suggestion_id: int, *, notes: str = ""):
        """Approve a suggestion."""
        await self.process_suggestion(ctx, suggestion_id, "approved", notes)

    @suggestions_group.command(name="reject")
    @commands.has_permissions(administrator=True)
    async def reject_suggestion(self, ctx, suggestion_id: int, *, notes: str = ""):
        """Reject a suggestion."""
        await self.process_suggestion(ctx, suggestion_id, "rejected", notes)

    async def process_suggestion(self, ctx, suggestion_id: int, new_status: str, notes: str):
        """Process a suggestion (approve/reject)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get the suggestion
            cursor.execute("""
                SELECT suggestion_id, user_id, suggestion_type, content, status
                FROM suggestions 
                WHERE suggestion_id = ? AND guild_id = ?
            """, (suggestion_id, ctx.guild.id))
            
            suggestion = cursor.fetchone()
            if not suggestion:
                await ctx.send(f"❌ Suggestion {suggestion_id} not found.")
                return
            
            _, user_id, suggestion_type, content, current_status = suggestion
            
            if current_status != "pending":
                await ctx.send(f"❌ Suggestion {suggestion_id} has already been {current_status}.")
                return
            
            # Update suggestion status
            cursor.execute("""
                UPDATE suggestions 
                SET status = ?, reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?, review_notes = ?
                WHERE suggestion_id = ?
            """, (new_status, ctx.author.id, notes, suggestion_id))
            conn.commit()
        
        # Create response embed
        color = discord.Color.green() if new_status == "approved" else discord.Color.red()
        embed = discord.Embed(
            title=f"Suggestion {new_status.title()}",
            description=f"**ID:** {suggestion_id}\n**Type:** {suggestion_type}\n**Content:** {content}",
            color=color,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="Reviewed by", value=ctx.author.mention, inline=True)
        if notes:
            embed.add_field(name="Notes", value=notes, inline=False)
        
        await ctx.send(embed=embed)
        
        # If approved, process the suggestion
        if new_status == "approved":
            await self.handle_approved_suggestion(ctx, suggestion_type, content, user_id)
        
        # Notify the user who made the suggestion
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                user_embed = discord.Embed(
                    title=f"Your suggestion was {new_status}",
                    description=f"**Suggestion:** {content}",
                    color=color
                )
                if notes:
                    user_embed.add_field(name="Review Notes", value=notes, inline=False)
                await user.send(embed=user_embed)
        except:
            pass

    async def handle_approved_suggestion(self, ctx, suggestion_type: str, content: str, user_id: int):
        """Handle an approved suggestion by implementing it."""
        if suggestion_type == "at_response":
            # Get inter-bot communication cog
            ibc_cog = self.bot.get_cog('InterBotCommunication')
            if ibc_cog:
                # Send to both bots
                suggestion_data = {
                    "suggestion_type": "at_response",
                    "content": content,
                    "approved_by": str(ctx.author),
                    "suggested_by_id": user_id
                }
                
                # Send to other bot (Huginn)
                success = await ibc_cog.send_to_other_bot(
                    "suggestion_approved", 
                    suggestion_data, 
                    ctx.guild.id
                )
                
                # Also add to this bot (Muninn)
                await ibc_cog.add_at_response(content, ctx.guild.id)
                
                if success:
                    await ctx.send(f"✅ @ response '{content}' has been added to both bots!")
                else:
                    await ctx.send(f"⚠️ @ response '{content}' added to Muninn, but failed to sync to Huginn.")
            else:
                await ctx.send("❌ Inter-bot communication not available. Suggestion approved but not implemented.")

    @suggestions_group.command(name="stats")
    @commands.has_permissions(administrator=True)
    async def suggestion_stats(self, ctx):
        """Show suggestion statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM suggestions 
                WHERE guild_id = ?
                GROUP BY status
            """, (ctx.guild.id,))
            
            stats = dict(cursor.fetchall())
        
        embed = discord.Embed(
            title="Suggestion Statistics",
            color=discord.Color.blue()
        )
        
        for status in ["pending", "approved", "rejected"]:
            count = stats.get(status, 0)
            embed.add_field(name=status.title(), value=str(count), inline=True)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SuggestionSystem(bot))
