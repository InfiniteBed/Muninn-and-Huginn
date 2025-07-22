import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.command_details = {
            "General Commands": {
                "shorthands": ["general", "gnrl"],
                "commands": {
                    "rankings": {"description": "`!rankings` - Show the rankings of users based on message count."},
                    "statistics": {"description": "`!statistics` - Show a user's message statistics."},
                    "graphs": {"description": "`!graphs` - Show statistics graphs that can be displayed."},
                    "contribute": {"description": "`!contribute` - Contribute ideas for the bot owner to implement into Huginn and Muninn."},
                    "submit": {"description": "`!submit` - Submit emojis to be voted on."}
                }
            },
            "Faith & Devotion": {
                "shorthands": ["faith", "devotion"],
                "commands": {
                    "submit_devotion": {"description": "`!submit_devotion` - Submit your daily devotion response (Bible reading/prayer time)."},
                    "devotion": {"description": "`!devotion` - Manually send the daily devotion accountability check-in."},
                    "devotion_stats": {"description": "`!devotion_stats [days]` - View server devotion statistics for the last X days (max 30)."},
                    "my_devotions": {"description": "`!my_devotions [days]` - View your personal devotion history for the last X days (max 30)."},
                    "devotion_setup": {"description": "`!devotion_setup` - View and configure devotion settings (Admin only)."},
                    "devotion_help": {"description": "`!devotion_help` - Detailed help for the devotion accountability system."}
                }
            },
            "Server Configuration": {
                "shorthands": ["config", "settings"],
                "commands": {
                    "config": {
                        "description": "`!config` - Server configuration commands (Admin only).",
                        "subcommands": {
                            "list": "`!config list` - Show all current server settings.",
                            "get": "`!config get <key>` - Get a specific configuration value.",
                            "delete": "`!config delete <key>` - Delete a configuration value.",
                            "devotion_channel": "`!config devotion_channel <#channel>` - Set the devotion channel."
                        }
                    }
                }
            },
            "RPG Commands": {
                "shorthands": ["rpg"],
                "commands": {
                    "profile_setup": {
                        "description": "`!profile_setup` - Start the full profile setup process.",
                        "subcommands": {
                            "class": "`!profile_setup_class` - Choose your character's class.",
                            "race": "`!profile_setup_race` - Choose your character's race.",
                            "name": "`!profile_setup_name` - Choose your character's name.",
                            "alignment": "`!profile_setup_alignment` - Choose your character's alignment.",
                            "abilities": "`!profile_setup_abilities` - Choose whether to roll or use point-buy for ability scores.",
                            "image": "`!profile_setup_image` - Upload your character's profile image.",
                            "gender": "`!profile_setup_gender` - Change your character's gender."
                        }
                    },
                    "me": {"description": "`!me` - Show the status of your character."},
                    "shop": {"description": "`!shop` - Visit the shop."},
                    "board": {"description": "`!board` - Visit the expedition board, where you can take on expeditions for money."},
                    "battle": {"description": "`!battle (Player)` - Battle another player for cash."}
                }
            },
            "Memorization Commands": {
                "shorthands": ["memorization", "mem"],
                "commands": {
                    "create_set": {"description": "`!create_set <group> <set_name> <skip_non_essential> <memorization_types>` - Create a new memorization set."},
                    "add_item": {"description": "`!add_item <group> <set_name> <title> <body> <solutions>` - Add an item to a memorization set."},
                    "practice": {"description": "`!practice [group]` - Start practicing a memorization set."}
                }
            },
            "Music Commands": {
                "shorthands": ["music", "audio"],
                "commands": {
                    "play": {"description": "`!play <song/url>` - Play a song, YouTube playlist, or add to queue. Aliases: `!p`"},
                    "pause": {"description": "`!pause` - Pause the current song."},
                    "resume": {"description": "`!resume` - Resume the paused song."},
                    "skip": {"description": "`!skip` - Skip the current song. Aliases: `!s`"},
                    "queue": {"description": "`!queue` - Show the current queue. Aliases: `!q`"},
                    "nowplaying": {"description": "`!nowplaying` - Show current song info. Aliases: `!np`"},
                    "songinfo": {"description": "`!songinfo` - Show detailed song information with metadata. Aliases: `!song`, `!info`"},
                    "volume": {"description": "`!volume [0-100]` - Change or show volume. Aliases: `!vol`"},
                    "loop": {"description": "`!loop` - Toggle loop mode for current song."},
                    "automesh": {"description": "`!automesh` - Toggle automesh mode (cycles songs by person). Aliases: `!am`"},
                    "autoducking": {"description": "`!autoducking` - Toggle auto ducking (lowers volume when someone speaks). Aliases: `!duck`"},
                    "clear": {"description": "`!clear` - Clear the queue."},
                    "stop": {"description": "`!stop` - Stop music and disconnect."},
                    "reconnect": {"description": "`!reconnect` - Force reconnect to voice channel."},
                    "musichelp": {"description": "`!musichelp` - Show detailed music commands help. Aliases: `!mhelp`"}
                }
            }
        }

    @commands.command()
    async def helpme(self, ctx, command=None):
        if command:
            # Check if the command matches a section or its shorthand
            for section, details in self.command_details.items():
                if command.lower() == section.lower() or command.lower() in details.get("shorthands", []):
                    embed = discord.Embed(
                        title=f"Help for `{section}`",
                        description="Here are the commands in this section:",
                        color=discord.Color.blue()
                    )
                    for cmd, cmd_details in details["commands"].items():
                        embed.add_field(
                            name=cmd,
                            value=cmd_details["description"],  # Only show the top-level description
                            inline=False
                        )
                    await ctx.send(embed=embed)
                    return

            # Check if the command matches an individual command or subcommand
            for section, details in self.command_details.items():
                for cmd, cmd_details in details["commands"].items():
                    if command.lower() == cmd:
                        embed = discord.Embed(
                            title=f"Help for `{command}`",
                            description=cmd_details["description"],
                            color=discord.Color.blue()
                        )
                        if "subcommands" in cmd_details:
                            embed.add_field(
                                name="Subcommands",
                                value="\n".join(cmd_details["subcommands"].values()),
                                inline=False
                            )
                        await ctx.send(embed=embed)
                        return
                    if "subcommands" in cmd_details and command.lower() in cmd_details["subcommands"]:
                        embed = discord.Embed(
                            title=f"Help for `{command}`",
                            description=cmd_details["subcommands"][command.lower()],
                            color=discord.Color.blue()
                        )
                        await ctx.send(embed=embed)
                        return

            # Command not found
            description = "Command not found."
            embed = discord.Embed(
                title=f"Help for `{command}`",
                description=description,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Display all commands
        embed = discord.Embed(
            title="Help Command",
            description="Here are all the available commands.",
            color=discord.Color.blue()
        )
        for section, details in self.command_details.items():
            embed.add_field(
                name=section,
                value="\n".join(cmd["description"] for cmd in details["commands"].values()),
                inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
