"""Cog: Sistema de tickets de compra.

Fluxo:
1) create_ticket() é chamado pelo cog menu_set quando alguém clica em comprar.
2) Cria canal privado, dá cargo_compra ao usuário.
3) Embed de confirmação (Confirmar / Cancelar).
4) Ao confirmar -> mostra PIX + botão "Confirmar Pagamento" (visível só admin/cargo).
5) Admin confirma -> entrega produto na DM, retira do estoque, remove cargo, fecha ticket.
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
    """Quem pode confirmar pagamento: admin OR portador do cargo de compra (admins do servidor que tenham o cargo)."""
    if is_admin(member.id):
        return True
    cargo_id = menu.get("cargo_compra", 0)
    if cargo_id and any(r.id == cargo_id for r in member.roles):
        # mas só se for staff do bot — usuários comuns também recebem o cargo, então adicionamos
        # como segurança extra: precisa ter manage_channels OR ser admin do bot
        if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
            return True
    return False


# ===== Views =====
class ConfirmOrderView(discord.ui.View):
    def __init__(self, menu_name: str, ci: int, pi: int, user_id: int):
        super().__init__(timeout=None)
        self.menu_name = menu_name
        self.ci = ci
        self.pi = pi
        self.user_id = user_id

        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name, {})
        confirm_style = hex_to_button_style(menu.get("cor_botao_comprar", "#57F287"))
        cancel_style = hex_to_button_style(menu.get("cor_botao_cancelar", "#ED4245"))

        emoji_conf = menu.get("emojis", {}).get("emoji_confirmar", "✅")
        emoji_canc = menu.get("emojis", {}).get("emoji_cancelar", "❌")

        b1 = discord.ui.Button(label="Confirmar pedido", style=confirm_style,
                               emoji=parse_emoji(emoji_conf),
                               custom_id=f"order_confirm:{menu_name}:{ci}:{pi}:{user_id}")
        b2 = discord.ui.Button(label="Cancelar", style=cancel_style,
                               emoji=parse_emoji(emoji_canc),
                               custom_id=f"order_cancel:{menu_name}:{ci}:{pi}:{user_id}")
        b1.callback = self._on_confirm
        b2.callback = self._on_cancel
        self.add_item(b1)
        self.add_item(b2)

    async def _on_confirm(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            return await interaction.response.send_message("❌ Apenas o comprador pode confirmar.", ephemeral=True)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.show_pix(interaction, self.menu_name, self.ci, self.pi, self.user_id)

    async def _on_cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id and not is_admin(interaction.user.id):
            return await interaction.response.send_message("❌ Apenas o comprador ou um admin pode cancelar.", ephemeral=True)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.close_ticket(interaction, reason="Cancelado pelo usuário.")


class PixView(discord.ui.View):
    def __init__(self, menu_name: str, ci: int, pi: int, user_id: int):
        super().__init__(timeout=None)
        self.menu_name = menu_name
        self.ci = ci
        self.pi = pi
        self.user_id = user_id

        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name, {})
        confirm_style = hex_to_button_style(menu.get("cor_botao_comprar", "#57F287"))
        cancel_style = hex_to_button_style(menu.get("cor_botao_cancelar", "#ED4245"))
        emoji_conf = menu.get("emojis", {}).get("emoji_confirmar", "✅")
        emoji_canc = menu.get("emojis", {}).get("emoji_cancelar", "❌")

        b1 = discord.ui.Button(label="Confirmar pagamento", style=confirm_style,
                               emoji=parse_emoji(emoji_conf),
                               custom_id=f"pay_confirm:{menu_name}:{ci}:{pi}:{user_id}")
        b2 = discord.ui.Button(label="Cancelar ticket", style=cancel_style,
                               emoji=parse_emoji(emoji_canc),
                               custom_id=f"pay_cancel:{menu_name}:{ci}:{pi}:{user_id}")
        b1.callback = self._on_confirm
        b2.callback = self._on_cancel
        self.add_item(b1)
        self.add_item(b2)

    async def _on_confirm(self, interaction: discord.Interaction):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(self.menu_name, {})
        if not _can_confirm_payment(interaction.user, menu):
            return await interaction.response.send_message(
                "❌ Apenas admins ou staff com o cargo configurado podem confirmar pagamentos.",
                ephemeral=True,
            )
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.deliver_product(interaction, self.menu_name, self.ci, self.pi, self.user_id)

    async def _on_cancel(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("❌ Apenas admins podem cancelar nessa etapa.", ephemeral=True)
        cog: "Tickets" = interaction.client.get_cog("Tickets")
        await cog.close_ticket(interaction, reason="Cancelado por admin.")


# ===== Cog =====
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------- Criar ticket ---------
    async def create_ticket(self, interaction: discord.Interaction, menu_name: str, ci: int, pi: int):
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            return await interaction.response.send_message("❌ Use no servidor.", ephemeral=True)

        existing = _has_open_ticket(user.id, guild.id)
        if existing:
            return await interaction.response.send_message(
                f"⚠️ Você já tem um ticket aberto: <#{existing}>", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name)
        if not menu:
            return await interaction.followup.send("❌ Menu não encontrado.", ephemeral=True)
        prod = menu["categorias"][ci]["produtos"][pi]

        # Permissões do canal
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                  manage_channels=True, manage_messages=True),
        }
        cargo_id = menu.get("cargo_compra", 0)
        cargo_obj = guild.get_role(cargo_id) if cargo_id else None
        # Importante: o cargo de "Cliente em Compra" será dado ao próprio usuário,
        # então NÃO damos visibilidade do canal por esse cargo (senão todos comprando se vêem).
        # Em vez disso, damos visibilidade aos admins do bot:
        from utils import get_config
        cfg = get_config()
        for admin_id in [cfg.get("OWNER_ID")] + cfg.get("ADMINS", []):
            m = guild.get_member(admin_id) if admin_id else None
            if m:
                overwrites[m] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True, manage_messages=True
                )

        category = None
        if menu.get("categoria_tickets"):
            category = guild.get_channel(menu["categoria_tickets"])
            if not isinstance(category, discord.CategoryChannel):
                category = None

        try:
            ch = await guild.create_text_channel(
                name=f"compra-{_slug(user.name)}",
                overwrites=overwrites,
                category=category,
                topic=f"Ticket de compra de {user} • {prod['nome']}",
                reason=f"Ticket de compra criado por {user}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ Não tenho permissão para criar canais. Verifique minhas permissões.", ephemeral=True
            )

        # Adiciona o cargo ao usuário (cargo "Cliente em Compra")
        if cargo_obj:
            try:
                await user.add_roles(cargo_obj, reason="Abriu ticket de compra")
            except discord.Forbidden:
                pass

        # Salva ticket
        tickets = load_json(TICKETS_PATH, {})
        tickets[str(ch.id)] = {
            "user_id": user.id,
            "guild_id": guild.id,
            "menu_name": menu_name,
            "ci": ci, "pi": pi,
            "open": True,
            "stage": "confirm",
        }
        save_json(TICKETS_PATH, tickets)

        # Embed inicial
        emoji_carrinho = menu["emojis"].get("emoji_carrinho", "🛒")
        embed = discord.Embed(
            title=f"{emoji_carrinho} Confirmação de Pedido",
            description=(
                f"Olá {user.mention}! Aqui está o resumo do seu pedido:\n\n"
                f"**Produto:** {prod['nome']}\n"
                f"**Descrição:** {prod.get('descricao') or '*sem descrição*'}\n"
                f"**Preço:** R$ {prod['preco']:.2f}\n\n"
                f"Clique em **Confirmar pedido** para prosseguir ao pagamento."
            ),
            color=hex_to_int(menu["cor"]),
        )
        if menu.get("banner_url"):
            embed.set_image(url=menu["banner_url"])
        embed.set_footer(text=f"Ticket de {user}", icon_url=user.display_avatar.url)

        view = ConfirmOrderView(menu_name, ci, pi, user.id)
        await ch.send(content=user.mention, embed=embed, view=view)
        await interaction.followup.send(f"✅ Seu ticket foi criado: {ch.mention}", ephemeral=True)

    # --------- Mostrar PIX ---------
    async def show_pix(self, interaction: discord.Interaction, menu_name: str, ci: int, pi: int, user_id: int):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name)
        if not menu:
            return await interaction.response.send_message("❌ Menu não encontrado.", ephemeral=True)
        prod = menu["categorias"][ci]["produtos"][pi]

        emoji_pix = menu["emojis"].get("emoji_pix", "💸")
        pix_key = menu.get("pix_key") or "*chave PIX não configurada*"

        embed = discord.Embed(
            title=f"{emoji_pix} Pagamento via PIX",
            description=(
                f"**Produto:** {prod['nome']}\n"
                f"**Valor:** R$ {prod['preco']:.2f}\n\n"
                f"**Chave PIX:**\n```{pix_key}```\n"
                f"Após realizar o pagamento, aguarde a confirmação de um admin.\n"
                f"O botão **Confirmar pagamento** é visível apenas para a equipe."
            ),
            color=hex_to_int(menu["cor"]),
        )
        embed.set_footer(text="Pague exatamente o valor acima.")
        view = PixView(menu_name, ci, pi, user_id)

        # atualiza estágio
        tickets = load_json(TICKETS_PATH, {})
        if str(interaction.channel.id) in tickets:
            tickets[str(interaction.channel.id)]["stage"] = "payment"
            save_json(TICKETS_PATH, tickets)

        await interaction.response.edit_message(embed=embed, view=view)

    # --------- Entregar produto ---------
    async def deliver_product(self, interaction: discord.Interaction, menu_name: str, ci: int, pi: int, user_id: int):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(menu_name)
        if not menu:
            return await interaction.response.send_message("❌ Menu não encontrado.", ephemeral=True)
        prod = menu["categorias"][ci]["produtos"][pi]
        estoque = prod.get("estoque", [])
        if not estoque:
            return await interaction.response.send_message(
                "❌ Estoque vazio! Reponha o produto antes de confirmar.", ephemeral=True
            )

        item = estoque.pop(0)
        save_json(MENUS_PATH, menus)

        guild = interaction.guild
        user = guild.get_member(user_id) or await self.bot.fetch_user(user_id)

        # Embed de entrega na DM
        emoji_entrega = menu["emojis"].get("emoji_entrega", "📦")
        dm_embed = discord.Embed(
            title=f"{emoji_entrega} Aqui está seu produto!",
            description=(
                f"Obrigado pela sua compra! 💚\n\n"
                f"**Produto:** {prod['nome']}\n"
                f"**Descrição:** {prod.get('descricao') or '—'}\n"
                f"**Valor pago:** R$ {prod['preco']:.2f}\n\n"
                f"**Conteúdo entregue:**\n```{item}```"
            ),
            color=hex_to_int(menu["cor"]),
        )
        if menu.get("banner_url"):
            dm_embed.set_image(url=menu["banner_url"])
        dm_embed.set_footer(text="Guarde estes dados em segurança.")

        dm_ok = True
        try:
            await user.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            dm_ok = False

        # Remove cargo
        cargo_id = menu.get("cargo_compra", 0)
        if cargo_id and isinstance(user, discord.Member):
            cargo = guild.get_role(cargo_id)
            if cargo and cargo in user.roles:
                try:
                    await user.remove_roles(cargo, reason="Compra finalizada")
                except discord.Forbidden:
                    pass

        # Mensagem no canal
        if dm_ok:
            await interaction.response.send_message(
                f"✅ Produto entregue na DM de {user.mention}. Encerrando ticket em 5s...",
            )
        else:
            # Se falhou DM, entrega no canal mesmo
            await interaction.response.send_message(
                f"⚠️ Não consegui enviar DM. Entregando aqui:",
                embed=dm_embed,
            )

        await asyncio.sleep(5)
        await self._do_close(interaction.channel, reason="Compra finalizada.")

    # --------- Fechar ticket ---------
    async def close_ticket(self, interaction: discord.Interaction, reason: str = "Ticket fechado."):
        await interaction.response.send_message(f"🔒 {reason} Encerrando em 3s...")
        await asyncio.sleep(3)
        await self._do_close(interaction.channel, reason=reason)

    async def _do_close(self, channel: discord.TextChannel, reason: str = ""):
        tickets = load_json(TICKETS_PATH, {})
        info = tickets.get(str(channel.id))
        if info:
            # remove cargo se ainda tem
            menus = load_json(MENUS_PATH, {})
            menu = menus.get(info["menu_name"], {})
            cargo_id = menu.get("cargo_compra", 0)
            if cargo_id:
                guild = channel.guild
                member = guild.get_member(info["user_id"])
                cargo = guild.get_role(cargo_id)
                if member and cargo and cargo in member.roles:
                    try:
                        await member.remove_roles(cargo, reason="Ticket encerrado")
                    except discord.Forbidden:
                        pass
            info["open"] = False
            tickets[str(channel.id)] = info
            save_json(TICKETS_PATH, tickets)

        try:
            await channel.delete(reason=reason)
        except discord.HTTPException:
            pass

    # --------- Comando /cancelar ---------
    @app_commands.command(name="cancelar", description="[ADMIN] Cancela o ticket de compra atual.")
    async def cancelar(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("❌ Apenas admins.", ephemeral=True)
        tickets = load_json(TICKETS_PATH, {})
        if str(interaction.channel.id) not in tickets:
            return await interaction.response.send_message("❌ Este canal não é um ticket de compra.", ephemeral=True)
        await self.close_ticket(interaction, reason="Ticket cancelado manualmente por um admin.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
