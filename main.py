"""
Bot de Vendas Discord - Entry Point
Autor: gerado para o projeto do cliente
"""
import asyncio
import os
import discord
from discord.ext import commands, tasks

from utils import get_config


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.dm_messages = True


class SalesBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        # Carrega cogs
        for cog in ("cogs.permissions", "cogs.menu_config", "cogs.menu_set", "cogs.tickets"):
            try:
                await self.load_extension(cog)
                print(f"[OK] Cog carregada: {cog}")
            except Exception as e:
                print(f"[ERRO] Falha ao carregar {cog}: {e}")

        # Sincroniza slash commands
        try:
            synced = await self.tree.sync()
            print(f"[OK] {len(synced)} slash commands sincronizados.")
        except Exception as e:
            print(f"[ERRO] Falha ao sincronizar comandos: {e}")

    async def on_ready(self):
        print("=" * 50)
        print(f"Bot online como: {self.user} (ID: {self.user.id})")
        print(f"Servidores: {len(self.guilds)}")
        print("=" * 50)
        if not self.update_status.is_running():
            self.update_status.start()

    @tasks.loop(seconds=10)
    async def update_status(self):
        messages = [
            "china ama lhayza ♥️",
            "Bot Payment v1",
            f"Estou em {len(self.guilds)} servidores"
        ]
        for msg in messages:
            await self.change_presence(
                activity=discord.Streaming(
                    name=msg,
                    url="https://www.twitch.tv/discord"
                )
            )
            await asyncio.sleep(10)


async def main():
    config = get_config()

    # 🔐 pega primeiro da variável de ambiente (Railway)
    token = os.getenv("TOKEN") or config.get("TOKEN")

    if not token or token == "COLE_SEU_TOKEN_AQUI":
        print("❌ Configure o TOKEN (variável de ambiente ou config.json).")
        return

    bot = SalesBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot encerrado.")
