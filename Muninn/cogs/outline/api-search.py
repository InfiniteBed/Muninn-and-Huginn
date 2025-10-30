import discord
from discord.ext import commands
import http.client as http
import json
import re
import datetime
from datetime import datetime

class APISearch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://api.bedrealm.com/search"
        self.api_key = "ol_api_6RC9dfkK2Tksjp8vThVWpF3iJDIxbJ4V8h7WCu"
        self.conn = http.HTTPSConnection("lore.bedrealm.com")    

    def get_test(self, query):
        payload = f"{{\"offset\":0,\"limit\":1,\"query\":\"{query}\"}}"

        headers = {
            'Content-Type': "application/json",
            'Authorization': f"Bearer {self.api_key}"
        }

        self.conn.request("POST", "/api/documents.search", payload, headers)

        res = self.conn.getresponse()
        data = res.read()
        
        if res.status == 200:
            parsed_data = json.loads(data.decode("utf-8"))
            
            if not parsed_data.get('data', []):
                return False
            
            document = parsed_data.get('data', [])[0].get('document', [])
            print(document)
            return document if document else False
        else:
            print(f"Error: {res.status} {res.reason}")
            print(data.decode("utf-8"))
            return False


    ## returns closest result from an Outline API search
    @commands.command(name='outline', aliases=['lore', 'ol'])
    async def outline(self, ctx, *, query: str):
        result = self.get_test(query)
        
        if not result:
            embed = discord.Embed(
                color=0x851919,
                title="No article found. Increase the specificity of your search.",
                timestamp=datetime.now(),
            )
            embed.set_author(
                name="Bedrealm Lore",
                url="https://lore.bedrealm.com",
                icon_url="https://id.bedrealm.com/api/oidc/clients/5ce64ed6-3849-4293-b069-a269394d8f9d/logo?light=false"
            )
            await ctx.send(embed=embed)
            return

        print(result)

        result_text = result.get('text', '')

        # get rid of everything in between pairs of :::; 
        result_text = re.sub(r':::.*?:::', '', result_text, flags=re.DOTALL)
        # strip excess newlines; 
        result_text = result_text + "..." if result else "No results found."
        # lock all headings to level 3 only;
        result_text = re.sub(r'^(#+)', r'###', result_text, flags=re.MULTILINE)
        # strip ![links] in this format
        result_text = re.sub(r'!\[.*?\]\((.*?)\)', '', result_text)
        # replace []() with hyperlink text; by adding https://lore.bedrealm.com/ before the () text; example  [Keepers](/doc/keepers-VBKFKmxmmi)
        result_text = re.sub(r'\[(.*?)\]\((.*?)\)', r'[\1](https://lore.bedrealm.com\2)', result_text)
        # strip multiple newlines before headings
        result_text = re.sub(r'\n{1,}', '\n', result_text)
        result_text = result_text.strip()
        result_text = result_text[:700] + "..." if len(result_text) > 700 else result_text
        
        embed = discord.Embed(
            color=0x851919,
            description=result_text,
            timestamp=datetime.now()
        )

        embed.set_author(
            name=result.get('title', ''),
            url=f"https://lore.bedrealm.com/{result.get('url')}",
            icon_url="https://id.bedrealm.com/api/oidc/clients/5ce64ed6-3849-4293-b069-a269394d8f9d/logo?light=false"
        )
        
        embed.set_footer(text="Bedrealm Lore")
            
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(APISearch(bot))