"""Cog: /perm — apenas o OWNER pode adicionar/remover admins."""
import discord
from discord import app_commands
from discord.ext import commands

from utils import get_config, save_config, is_owner


class Permissions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="perm", description="[OWNER] Adicionar ou remover admins do painel.")
    @app_commands.describe(acao="Adicionar ou remover", usuario="Usuário alvo")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Adicionar", value="add"),
        app_commands.Choice(name="Remover", value="remove"),
        app_commands.Choice(name="Listar", value="list"),
    ])
    async def perm(self, interaction: discord.Interaction,
                   acao: app_commands.Choice[str],
                   usuario: discord.User = None):
        # Restrição estrita ao OWNER_ID
        if not is_owner(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Apenas o **dono** (configurado no config.json) pode usar este comando.", ephemeral=True
            )

        config = get_config()
        admins = config.get("ADMINS", [])

        if acao.value == "list":
            if not admins:
                desc = "Nenhum admin configurado."
            else:
                desc = "\n".join(f"• <@{uid}> (`{uid}`)" for uid in admins)
            embed = discord.Embed(
                title="👑 Lista de Admins",
                description=desc,
                color=0x5865F2,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if usuario is None:
            return await interaction.response.send_message(
                "❌ Você precisa informar um usuário.", ephemeral=True
            )

        if acao.value == "add":
            if usuario.id in admins:
                return await interaction.response.send_message(
                    f"⚠️ {usuario.mention} já é admin.", ephemeral=True
                )
            admins.append(usuario.id)
            config["ADMINS"] = admins
            save_config(config)
            return await interaction.response.send_message(
                f"✅ {usuario.mention} foi adicionado aos admins.", ephemeral=True
            )

        if acao.value == "remove":
            if usuario.id not in admins:
                return await interaction.response.send_message(
                    f"⚠️ {usuario.mention} não é admin.", ephemeral=True
                )
            admins.remove(usuario.id)
            config["ADMINS"] = admins
            save_config(config)
            return await interaction.response.send_message(
                f"✅ {usuario.mention} foi removido dos admins.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Permissions(bot))
