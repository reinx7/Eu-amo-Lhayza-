"""Cog: /menu — painel de configuração ultra-rápido.
"""
import discord
from discord import app_commands
from discord.ext import commands
from utils import (
    load_json, save_json, MENUS_PATH, is_admin,
    hex_to_int, get_config, emoji_for_text, normalize_hex,
)

def default_menu() -> dict:
    return {
        "titulo": "🛒 Loja Premium", "descricao": "Selecione um produto.", "cor": "#5865F2",
        "banner_url": "", "tipo_selecao": "select", "cargo_compra": 0, "categoria_tickets": 0,
        "pix_key": "", "qr_code_url": "", "delivery_channel": 0, "feedback_channel": 0,
        "emojis": {"emoji_titulo": "🛒", "emoji_categoria": "📁", "emoji_produto": "🛍️", "emoji_comprar": "✅", "emoji_carrinho": "🛒", "emoji_pix": "💸", "emoji_confirmar": "✅", "emoji_cancelar": "❌", "emoji_entrega": "📦"},
        "cor_botao_comprar": "#57F287", "cor_botao_cancelar": "#ED4245", "categorias": [{"nome": "Geral", "emoji": "📁", "produtos": []}],
    }

def build_preview_embed(menu: dict, bot=None) -> discord.Embed:
    embed = discord.Embed(title=menu["titulo"], description=menu["descricao"], color=hex_to_int(menu["cor"]))
    for cat in menu["categorias"]:
        for p in cat["produtos"]:
            embed.add_field(name=p["nome"], value=f"R$ {p['preco']:.2f} | Estoque: {len(p['estoque'])}", inline=False)
    return embed

class ProdutoModal(discord.ui.Modal):
    def __init__(self, view, ci, pi=None):
        super().__init__(title="Gerenciar Produto")
        self.view, self.ci, self.pi = view, ci, pi
        p = view.menu["categorias"][ci]["produtos"][pi] if pi is not None else {"nome": "", "preco": "0.00", "estoque": []}
        self.nome = discord.ui.TextInput(label="Nome", default=p["nome"])
        self.preco = discord.ui.TextInput(label="Preço", default=str(p["preco"]))
        self.estoque = discord.ui.TextInput(label="Estoque (separe por VÍRGULA)", style=discord.TextStyle.paragraph, default=",".join(p["estoque"]))
        for i in [self.nome, self.preco, self.estoque]: self.add_item(i)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            preco = float(self.preco.value.replace(",", "."))
            estoque = [x.strip() for x in self.estoque.value.split(",") if x.strip()]
            data = {"nome": self.nome.value, "preco": preco, "emoji": "🛍️", "estoque": estoque}
            if self.pi is not None: self.view.menu["categorias"][self.ci]["produtos"][self.pi] = data
            else: self.view.menu["categorias"][self.ci]["produtos"].append(data)
            await self.view.refresh(interaction)
        except: await interaction.response.send_message("Erro nos dados!", ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self, menu, bot):
        super().__init__(timeout=None)
        self.menu, self.bot = menu, bot
        self._build()

    def _build(self):
        self.clear_items()
        # Select para escolher produto para EDITAR ou REMOVER
        prods = []
        for ci, cat in enumerate(self.menu["categorias"]):
            for pi, p in enumerate(cat["produtos"]):
                prods.append(discord.SelectOption(label=p["nome"], value=f"{ci}:{pi}", description=f"R$ {p['preco']}"))
        
        if prods:
            sel = discord.ui.Select(placeholder="📝 Editar/Remover Produto...", options=prods[:25])
            async def sel_cb(i):
                ci, pi = map(int, sel.values[0].split(":"))
                await i.response.send_modal(ProdutoModal(self, ci, pi))
            sel.callback = sel_cb
            self.add_item(sel)

        b_add = discord.ui.Button(label="➕ Add Produto", style=discord.ButtonStyle.success)
        b_add.callback = lambda i: i.response.send_modal(ProdutoModal(self, 0))
        
        b_del = discord.ui.Button(label="🗑️ Limpar Tudo", style=discord.ButtonStyle.danger)
        async def del_all(i):
            self.menu["categorias"][0]["produtos"] = []
            await self.refresh(i)
        b_del.callback = del_all

        b_save = discord.ui.Button(label="💾 Salvar", style=discord.ButtonStyle.primary)
        async def save_cb(i):
            m_name = self.menu.get("internal_name", "loja")
            menus = load_json(MENUS_PATH, {})
            menus[m_name] = self.menu
            save_json(MENUS_PATH, menus)
            await i.response.send_message("✅ Salvo!", ephemeral=True)
        b_save.callback = save_cb

        for b in [b_add, b_del, b_save]: self.add_item(b)

    async def refresh(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(embed=build_preview_embed(self.menu), view=self)

class MenuConfig(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="menu")
    async def menu(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id): return await interaction.response.send_message("❌", ephemeral=True)
        menus = load_json(MENUS_PATH, {})
        m = list(menus.values())[0] if menus else default_menu()
        if menus: m["internal_name"] = list(menus.keys())[0]
        else: m["internal_name"] = "loja"
        await interaction.response.send_message("⚙️ Painel Direto", embed=build_preview_embed(m), view=ConfigView(m, self.bot), ephemeral=True)

async def setup(bot): await bot.add_cog(MenuConfig(bot))
