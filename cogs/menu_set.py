"""Cog: /set — envia um menu salvo num canal e renderiza a view de compra."""
import discord
from discord import app_commands
from discord.ext import commands

from utils import (
    load_json, save_json, MENUS_PATH, is_admin,
    hex_to_int, hex_to_button_style, parse_emoji, emoji_for_text,
)


def build_public_embed(menu: dict, bot=None) -> discord.Embed:
    emoji_titulo = emoji_for_text(menu["emojis"].get("emoji_titulo", ""), bot)
    titulo = f"{emoji_titulo} {menu['titulo']}".strip() if emoji_titulo else menu["titulo"]
    embed = discord.Embed(
        title=titulo,
        description=menu["descricao"],
        color=hex_to_int(menu["cor"]),
    )
    if menu.get("banner_url"):
        embed.set_image(url=menu["banner_url"])
    
    if menu.get("tipo_selecao") != "select":
        for cat in menu["categorias"]:
            emoji_cat = emoji_for_text(cat.get("emoji") or menu["emojis"].get("emoji_categoria", ""), bot) or "📁"
            prods = cat.get("produtos", [])
            if not prods:
                continue
            linhas = []
            for p in prods:
                estoque = len(p.get("estoque", []))
                pe = emoji_for_text(p.get("emoji") or menu["emojis"].get("emoji_produto", ""), bot) or "🛍️"
                status = f"`{estoque} em estoque`" if estoque > 0 else "`ESGOTADO`"
                linhas.append(f"{pe} **{p['nome']}** — R$ {p['preco']:.2f} {status}")
            embed.add_field(name=f"{emoji_cat} {cat['nome']}", value="\n".join(linhas), inline=False)
    
    embed.set_footer(text="Selecione um produto abaixo para comprar.")
    return embed


class PublicMenuView(discord.ui.View):
    def __init__(self, menu_name: str, menu: dict, bot=None):
        super().__init__(timeout=None)
        self.menu_name = menu_name
        self.menu = menu
        self.bot = bot
        self._build()

    def _build(self):
        self.clear_items()
        if self.menu.get("tipo_selecao") == "select":
            self._build_select()
        else:
            self._build_buttons()

    def _all_products(self):
        out = []
        for ci, cat in enumerate(self.menu.get("categorias", [])):
            for pi, prod in enumerate(cat.get("produtos", [])):
                out.append((ci, pi, cat, prod))
        return out

    def _build_select(self):
        prods = self._all_products()
        if not prods:
            sel = discord.ui.Select(
                placeholder="⚠️ Nenhum produto disponível.",
                options=[discord.SelectOption(label="Sem produtos", value="none")],
                disabled=True,
                custom_id=f"public_select_empty:{self.menu_name}",
            )
            self.add_item(sel)
            return

        options = []
        for ci, pi, cat, prod in prods[:25]:
            estoque = len(prod.get("estoque", []))
            emoji_p = parse_emoji(prod.get("emoji") or self.menu["emojis"].get("emoji_produto", ""), self.bot)
            label = prod["nome"][:90] or "Produto"
            desc = f"{cat['nome']} • R$ {prod['preco']:.2f} • estoque: {estoque}"[:100]
            options.append(discord.SelectOption(
                label=label,
                value=f"{ci}:{pi}",
                description=desc,
                emoji=emoji_p or "🛍️",
            ))
        sel = discord.ui.Select(
            placeholder="🛒 Escolha um produto...",
            options=options,
            custom_id=f"public_select:{self.menu_name}",
        )
        sel.callback = self._on_select
        self.add_item(sel)

    def _build_buttons(self):
        prods = self._all_products()
        if not prods:
            btn = discord.ui.Button(label="Nenhum produto disponível", style=discord.ButtonStyle.secondary, disabled=True)
            self.add_item(btn)
            return
        style = hex_to_button_style(self.menu.get("cor_botao_comprar", "#57F287"))
        for ci, pi, cat, prod in prods[:25]:
            emoji_p = parse_emoji(prod.get("emoji") or self.menu["emojis"].get("emoji_comprar", ""), self.bot)
            btn = discord.ui.Button(
                label=f"{prod['nome'][:60]} — R$ {prod['preco']:.2f}",
                style=style,
                emoji=emoji_p or None,
                custom_id=f"public_btn:{self.menu_name}:{ci}:{pi}",
            )
            btn.callback = self._make_btn_cb(ci, pi)
            self.add_item(btn)

    def _make_btn_cb(self, ci: int, pi: int):
        async def cb(interaction: discord.Interaction):
            await self._open_ticket(interaction, ci, pi)
        return cb

    async def _on_select(self, interaction: discord.Interaction):
        # Correção: Pegar os valores antes de qualquer defer
        vals = interaction.data.get("values")
        if not vals: return
        
        ci, pi = map(int, vals[0].split(":"))
        
        # Abrir o ticket
        await self._open_ticket(interaction, ci, pi)
        
        # Resetar a view para permitir nova seleção sem travar
        try:
            # Re-instanciar a view limpa o estado de seleção do select menu no Discord
            new_view = PublicMenuView(self.menu_name, self.menu, self.bot)
            await interaction.edit_original_response(view=new_view)
        except:
            pass

    async def _open_ticket(self, interaction: discord.Interaction, ci: int, pi: int):
        menus = load_json(MENUS_PATH, {})
        menu = menus.get(self.menu_name)
        if not menu:
            return await interaction.response.send_message("❌ Menu não encontrado.", ephemeral=True)
        try:
            cat = menu["categorias"][ci]
            prod = cat["produtos"][pi]
        except (IndexError, KeyError):
            return await interaction.response.send_message("❌ Produto inválido.", ephemeral=True)
        
        if not prod.get("estoque"):
            return await interaction.response.send_message("❌ Esse produto está esgotado.", ephemeral=True)

        tickets_cog = interaction.client.get_cog("Tickets")
        if not tickets_cog:
            return await interaction.response.send_message("❌ Sistema de tickets indisponível.", ephemeral=True)
        
        await tickets_cog.create_ticket(interaction, self.menu_name, ci, pi)


class MenuSet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="set", description="[ADMIN] Envia um menu de vendas salvo no canal atual.")
    async def set_menu(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("❌ Apenas admins.", ephemeral=True)

        menus = load_json(MENUS_PATH, {})
        if not menus:
            return await interaction.response.send_message("❌ Nenhum menu salvo.", ephemeral=True)

        options = [discord.SelectOption(label=name[:90], value=name) for name in menus.keys()]
        sel = discord.ui.Select(placeholder="Escolha o menu para enviar...", options=options)

        async def cb(interaction2: discord.Interaction):
            name = sel.values[0]
            menu = menus[name]
            embed = build_public_embed(menu, self.bot)
            view = PublicMenuView(name, menu, self.bot)
            await interaction2.channel.send(embed=embed, view=view)
            await interaction2.response.edit_message(content=f"✅ Menu **{name}** enviado!", view=None)

        sel.callback = cb
        view = discord.ui.View(timeout=120); view.add_item(sel)
        await interaction.response.send_message("Selecione o menu:", view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MenuSet(bot))
    menus = load_json(MENUS_PATH, {})
    for name, menu in menus.items():
        bot.add_view(PublicMenuView(name, menu, bot))
