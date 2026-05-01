"""Cog: Sistema de tickets de compra.
"""
import asyncio
import re
import discord
from discord import app_commands
from discord.ext import commands

from utils import (
    load_json, save_json, MENUS_PATH, TICKETS_PATH,
    is_admin, hex_to_int, hex_to_button_style, parse_emoji,
)


# ----- helpers -----
def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", s.lower()).strip("-")
    return s[:40] or "compra"


def _has_open_ticket(user_id: int, guild_id: int) -> int | None:
    tickets = load_json(TICKETS_PATH, {})
    for ch_id, info in tickets.items():
        if info.get("user_id") == user_id and info.get("guild_id") == guild_id and info.get("open"):
            return int(ch_id)
    return None


def _can_confirm_payment(member: discord.Member, menu: dict) -> bool:
    # Apenas admins ou o dono podem aprovar
    if is_admin(member.id): return True
    # Se houver um cargo específico configurado, membros com esse cargo também podem aprovar
    cargo_id = menu.get("cargo_compra", 0)
    if cargo_id and any(r.id == cargo_id for r in member.roles):
        return True
    return False


# ===== Views =====
class FeedbackModal(discord.ui.Modal, title="Enviar Feedback"):
    def __init__(self, menu: dict):
        super().__init__()
        self.menu = menu
        self.estrelas = discord.ui.TextInput(label="Estrelas (1 a 5)", placeholder="⭐⭐⭐⭐⭐", min_length=1, max_length=1, required=True)
        self.comentario = discord.ui.TextInput(label="Comentário", style=discord.TextStyle.paragraph, placeholder="O que achou do produto?", required=True)
        self.add_item(self.estrelas)
        self.add_item(self.comentario)

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = self.menu.get("feedback_channel")
        if not channel_id:
            return await interaction.response.send_message("❌ Canal de feedback não configurado.", ephemeral=True)
        
        channel = interaction.client.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Canal de feedback não encontrado.", ephemeral=True)
        
        embed = discord.Embed(
            title="⭐ Novo Feedback!",
            description=f"**Usuário:** {interaction.user.mention} ({interaction.user.id})\n"
                        f"**Avaliação:** {self.estrelas.value} estrelas\n"
                        f"**Comentário:**\n{self.comentario.value}",
            color=hex_to_int(self.menu["cor"])
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Obrigado pelo seu feedback!", ephemeral=True)


class ConfirmOrderView(discord.ui.View):
    def __init__(self, menu_name: str, ci: int, pi: int, user_id: int):
        super().__init__(timeout=None)
        self.menu_name = menu_name
        self.ci = ci
        self.pi = pi
        self.user_id = user_id
        self._setup_buttons()

    def _setup_buttons(self):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(self.menu_name, {})
        confirm_style = hex_to_button_style(menu.get("cor_botao_comprar", "#57F287"))
        cancel_style = hex_to_button_style(menu.get("cor_botao_cancelar", "#ED4245"))
        
        b1 = discord.ui.Button(label="Confirmar pedido", style=confirm_style, emoji="✅", custom_id=f"conf_{self.menu_name}_{self.ci}_{self.pi}")
        b2 = discord.ui.Button(label="Cancelar", style=cancel_style, emoji="❌", custom_id=f"canc_{self.menu_name}_{self.ci}_{self.pi}")
        
        async def conf_cb(i: discord.Interaction):
            if i.user.id != self.user_id: return await i.response.send_message("❌ Não é seu.", ephemeral=True)
            await i.client.get_cog("Tickets").show_pix(i, self.menu_name, self.ci, self.pi, self.user_id)
        
        async def canc_cb(i: discord.Interaction):
            # Usuário ou Admin podem cancelar
            if i.user.id != self.user_id and not is_admin(i.user.id): 
                return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
            await i.client.get_cog("Tickets").close_ticket(i, reason="Cancelado.")
            
        b1.callback = conf_cb; b2.callback = canc_cb
        self.add_item(b1); self.add_item(b2)


class PixView(discord.ui.View):
    def __init__(self, menu_name: str, ci: int, pi: int, user_id: int):
        super().__init__(timeout=None)
        self.menu_name = menu_name
        self.ci = ci
        self.pi = pi
        self.user_id = user_id
        self._setup_buttons()

    def _setup_buttons(self):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(self.menu_name, {})
        confirm_style = hex_to_button_style(menu.get("cor_botao_comprar", "#57F287"))
        cancel_style = hex_to_button_style(menu.get("cor_botao_cancelar", "#ED4245"))
        
        b1 = discord.ui.Button(label="Confirmar pagamento", style=confirm_style, emoji="✅", custom_id=f"pay_{self.menu_name}_{self.ci}_{self.pi}")
        b2 = discord.ui.Button(label="Cancelar", style=cancel_style, emoji="❌", custom_id=f"canc_pix_{self.menu_name}_{self.ci}_{self.pi}")
        
        async def pay_cb(i: discord.Interaction):
            if not _can_confirm_payment(i.user, menu):
                return await i.response.send_message("❌ Apenas staff.", ephemeral=True)
            await i.client.get_cog("Tickets").deliver_product(i, self.menu_name, self.ci, self.pi, self.user_id)
            
        async def canc_cb(i: discord.Interaction):
            if i.user.id != self.user_id and not is_admin(i.user.id): 
                return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
            await i.client.get_cog("Tickets").close_ticket(i, reason="Cancelado.")
            
        b1.callback = pay_cb; b2.callback = canc_cb
        self.add_item(b1); self.add_item(b2)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def create_ticket(self, interaction: discord.Interaction, menu_name: str, ci: int, pi: int):
        guild = interaction.guild
        user = interaction.user
        
        existing = _has_open_ticket(user.id, guild.id)
        if existing: return await interaction.response.send_message(f"⚠️ Ticket aberto: <#{existing}>", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name)
        prod = menu["categorias"][ci]["produtos"][pi]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        
        # Adicionar admins às permissões
        from utils import get_config
        cfg = get_config()
        owner_id = cfg.get("OWNER_ID")
        if owner_id:
            m = guild.get_member(owner_id)
            if m: overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
        
        for admin_id in cfg.get("ADMINS", []):
            m = guild.get_member(admin_id)
            if m: overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

        category = guild.get_channel(menu.get("categoria_tickets")) if menu.get("categoria_tickets") else None
        ch = await guild.create_text_channel(name=f"compra-{_slug(user.name)}", overwrites=overwrites, category=category)

        # Cargo ao abrir ticket
        cargo_id = menu.get("cargo_compra")
        if cargo_id:
            cargo = guild.get_role(cargo_id)
            if cargo: await user.add_roles(cargo, reason="Abriu ticket")

        tickets = load_json(TICKETS_PATH, {})
        tickets[str(ch.id)] = {"user_id": user.id, "guild_id": guild.id, "menu_name": menu_name, "ci": ci, "pi": pi, "open": True}
        save_json(TICKETS_PATH, tickets)

        embed = discord.Embed(
            title="🛒 Confirmação de Pedido",
            description=f"Olá {user.mention}!\n\n**Produto:** {prod['nome']}\n**Preço:** R$ {prod['preco']:.2f}\n\nClique abaixo para prosseguir.",
            color=hex_to_int(menu["cor"])
        )
        if menu.get("banner_url"): embed.set_image(url=menu["banner_url"])
        
        await ch.send(content=user.mention, embed=embed, view=ConfirmOrderView(menu_name, ci, pi, user.id))
        await interaction.followup.send(f"✅ Ticket criado: {ch.mention}", ephemeral=True)

    async def show_pix(self, interaction: discord.Interaction, menu_name: str, ci: int, pi: int, user_id: int):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name)
        prod = menu["categorias"][ci]["produtos"][pi]
        pix_key = menu.get("pix_key") or "Não configurada"

        embed = discord.Embed(
            title="💸 Pagamento via PIX",
            description=f"**Produto:** {prod['nome']}\n**Valor:** R$ {prod['preco']:.2f}\n\n**Chave PIX:**\n`{pix_key}`",
            color=hex_to_int(menu["cor"])
        )
        if menu.get("qr_code_url"): embed.set_image(url=menu["qr_code_url"])
        
        await interaction.response.edit_message(embed=embed, view=PixView(menu_name, ci, pi, user_id))

    async def deliver_product(self, interaction: discord.Interaction, menu_name: str, ci: int, pi: int, user_id: int):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name)
        prod = menu["categorias"][ci]["produtos"][pi]
        
        if not prod["estoque"]:
            return await interaction.response.send_message("❌ Estoque vazio!", ephemeral=True)
        
        item = prod["estoque"].pop(0)
        save_json(MENUS_PATH, menus)

        user = interaction.guild.get_member(user_id) or await self.bot.fetch_user(user_id)
        
        dm_embed = discord.Embed(
            title="📦 Produto Entregue!",
            description=f"Obrigado! 💚\n\n**Produto:** {prod['nome']}\n**Conteúdo:**\n```{item}```",
            color=hex_to_int(menu["cor"])
        )
        
        view_dm = discord.ui.View()
        btn_fb = discord.ui.Button(label="Enviar Feedback", style=discord.ButtonStyle.primary, emoji="⭐")
        async def fb_cb(i: discord.Interaction):
            await i.response.send_modal(FeedbackModal(menu))
        btn_fb.callback = fb_cb
        view_dm.add_item(btn_fb)

        dm_ok = True
        try: await user.send(embed=dm_embed, view=view_dm)
        except: dm_ok = False

        deliv_id = menu.get("delivery_channel")
        if deliv_id:
            deliv_ch = self.bot.get_channel(deliv_id)
            if deliv_ch:
                log_embed = discord.Embed(
                    title="✅ Compra Aprovada!",
                    description=f"**Produto:** {prod['nome']}\n**Preço:** R$ {prod['preco']:.2f}\n**Cliente:** {user.mention} ({user.id})",
                    color=0x57F287
                )
                await deliv_ch.send(embed=log_embed)

        msg = f"✅ Entregue na DM de {user.mention}. Fechando em 30s..." if dm_ok else "⚠️ DM fechada. Entregue aqui. Fechando em 30s:"
        if interaction.response.is_done():
            await interaction.followup.send(msg, embed=None if dm_ok else dm_embed)
        else:
            await interaction.response.send_message(msg, embed=None if dm_ok else dm_embed)

        await asyncio.sleep(30)
        await self._do_close(interaction.channel)

    async def close_ticket(self, interaction: discord.Interaction, reason: str = "Fechado."):
        if interaction.response.is_done():
            await interaction.followup.send(f"🔒 {reason} Fechando em 3s...")
        else:
            await interaction.response.send_message(f"🔒 {reason} Fechando em 3s...")
        await asyncio.sleep(3)
        await self._do_close(interaction.channel)

    async def _do_close(self, channel: discord.TextChannel):
        tickets = load_json(TICKETS_PATH, {})
        info = tickets.get(str(channel.id))
        if info:
            info["open"] = False
            save_json(TICKETS_PATH, tickets)
            menus = load_json(MENUS_PATH, {})
            menu = menus.get(info["menu_name"], {})
            cargo_id = menu.get("cargo_compra")
            if cargo_id:
                member = channel.guild.get_member(info["user_id"])
                cargo = channel.guild.get_role(cargo_id)
                if member and cargo:
                    try: await member.remove_roles(cargo)
                    except: pass
        try: await channel.delete()
        except: pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
