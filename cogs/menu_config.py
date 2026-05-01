"""Cog: /menu — Painel Completo Restaurado com Melhorias de Produto.
"""
import discord
from discord import app_commands
from discord.ext import commands
from utils import (
    load_json, save_json, MENUS_PATH, is_admin,
    hex_to_int, get_config, parse_emoji, emoji_for_text, normalize_hex,
)

def default_menu() -> dict:
    return {
        "titulo": "🛒 Loja Premium", "descricao": "Selecione uma categoria.", "cor": "#5865F2",
        "banner_url": "", "tipo_selecao": "select", "cargo_compra": 0, "categoria_tickets": 0,
        "pix_key": "", "qr_code_url": "", "delivery_channel": 0, "feedback_channel": 0,
        "emojis": {"emoji_titulo": "🛒", "emoji_categoria": "📁", "emoji_produto": "🛍️", "emoji_comprar": "✅", "emoji_carrinho": "🛒", "emoji_pix": "💸", "emoji_confirmar": "✅", "emoji_cancelar": "❌", "emoji_entrega": "📦"},
        "cor_botao_comprar": "#57F287", "cor_botao_cancelar": "#ED4245", "categorias": [],
    }

def build_preview_embed(menu: dict, bot=None) -> discord.Embed:
    emoji_titulo = emoji_for_text(menu["emojis"].get("emoji_titulo", ""), bot)
    embed = discord.Embed(title=f"{emoji_titulo} {menu['titulo']}".strip(), description=menu["descricao"], color=hex_to_int(menu["cor"]))
    if menu.get("banner_url"): embed.set_image(url=menu["banner_url"])
    for cat in menu["categorias"]:
        emoji_cat = emoji_for_text(cat.get("emoji") or menu["emojis"].get("emoji_categoria", ""), bot) or "📁"
        prods = cat.get("produtos", [])
        if prods:
            linhas = [f"**{p['nome']}** — R$ {p['preco']:.2f} `({len(p['estoque'])})`" for p in prods]
            embed.add_field(name=f"{emoji_cat} {cat['nome']}", value="\n".join(linhas), inline=False)
    return embed

class TextosModal(discord.ui.Modal, title="Editar textos"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.t = discord.ui.TextInput(label="Título", default=view.menu["titulo"])
        self.d = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, default=view.menu["descricao"])
        self.c = discord.ui.TextInput(label="Cor HEX", default=view.menu["cor"])
        self.b = discord.ui.TextInput(label="Banner URL", default=view.menu.get("banner_url", ""), required=False)
        for i in [self.t, self.d, self.c, self.b]: self.add_item(i)
    async def on_submit(self, i):
        self.view.menu.update({"titulo": self.t.value, "descricao": self.d.value, "cor": normalize_hex(self.c.value), "banner_url": self.b.value})
        await self.view.refresh(i)

class ProdutoModal(discord.ui.Modal, title="Gerenciar Produto"):
    def __init__(self, view, ci, pi=None):
        super().__init__()
        self.view, self.ci, self.pi = view, ci, pi
        p = view.menu["categorias"][ci]["produtos"][pi] if pi is not None else {"nome": "", "preco": "0.00", "estoque": []}
        self.n = discord.ui.TextInput(label="Nome", default=p["nome"])
        self.p = discord.ui.TextInput(label="Preço", default=str(p["preco"]))
        self.e = discord.ui.TextInput(label="Estoque (separe por VÍRGULA)", style=discord.TextStyle.paragraph, default=",".join(p["estoque"]))
        for i in [self.n, self.p, self.e]: self.add_item(i)
    async def on_submit(self, i):
        try:
            data = {"nome": self.n.value, "preco": float(self.p.value.replace(",", ".")), "emoji": "🛍️", "estoque": [x.strip() for x in self.e.value.split(",") if x.strip()]}
            if self.pi is not None: self.view.menu["categorias"][self.ci]["produtos"][self.pi] = data
            else: self.view.menu["categorias"][self.ci]["produtos"].append(data)
            await self.view.refresh(i)
        except: await i.response.send_message("Erro!", ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self, menu, bot):
        super().__init__(timeout=None)
        self.menu, self.bot = menu, bot
        self._build()
    def _build(self):
        self.clear_items()
        sel = discord.ui.Select(placeholder="⚙️ Configurações...", options=[
            discord.SelectOption(label="Textos", value="textos", emoji="📝"),
            discord.SelectOption(label="Emojis", value="emojis", emoji="🎨"),
            discord.SelectOption(label="Cores Botões", value="cores", emoji="🎯"),
            discord.SelectOption(label="Tipo Seleção", value="tipo", emoji="🧩"),
            discord.SelectOption(label="Config Avançada", value="avancado", emoji="🔐"),
        ])
        async def sel_cb(i):
            v = sel.values[0]
            if v == "textos": await i.response.send_modal(TextosModal(self))
            elif v == "tipo": self.menu["tipo_selecao"] = "buttons" if self.menu["tipo_selecao"] == "select" else "select"; await self.refresh(i)
            else: await i.response.send_message("Use o painel completo para isso.", ephemeral=True)
        sel.callback = sel_cb
        self.add_item(sel)

        # Gerenciamento de Produtos Direto
        if not self.menu["categorias"]: self.menu["categorias"].append({"nome": "Geral", "emoji": "📁", "produtos": []})
        
        b_add = discord.ui.Button(label="➕ Add Produto", style=discord.ButtonStyle.success, row=1)
        b_add.callback = lambda i: i.response.send_modal(ProdutoModal(self, 0))
        
        b_save = discord.ui.Button(label="💾 Salvar", style=discord.ButtonStyle.primary, row=1)
        async def save_cb(i):
            menus = load_json(MENUS_PATH, {}); name = self.menu.get("internal_name", "loja")
            menus[name] = self.menu; save_json(MENUS_PATH, menus)
            await i.response.send_message("✅ Salvo!", ephemeral=True)
        b_save.callback = save_cb
        
        self.add_item(b_add); self.add_item(b_save)

    async def refresh(self, i):
        self._build()
        await i.response.edit_message(embed=build_preview_embed(self.menu), view=self)

class MenuConfig(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="menu")
    async def menu(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id): return await interaction.response.send_message("❌", ephemeral=True)
        menus = load_json(MENUS_PATH, {})
        m = list(menus.values())[0] if menus else default_menu()
        m["internal_name"] = list(menus.keys())[0] if menus else "loja"
        await interaction.response.send_message("⚙️ Painel Administrativo", embed=build_preview_embed(m), view=ConfigView(m, self.bot), ephemeral=True)

async def setup(bot): await bot.add_cog(MenuConfig(bot))
