"""Cog: /menu — painel de configuração do menu de vendas.
"""
import copy
import discord
from discord import app_commands
from discord.ext import commands

from utils import (
    load_json, save_json, MENUS_PATH, is_admin,
    hex_to_int, get_config, parse_emoji, emoji_for_text, normalize_hex,
)


# ---------- Estrutura padrão de um menu novo ----------
def default_menu() -> dict:
    return {
        "titulo": "🛒 Loja Premium",
        "descricao": "Selecione uma categoria abaixo para ver nossos produtos.",
        "cor": "#5865F2",
        "banner_url": "",
        "tipo_selecao": "select",
        "cargo_compra": 0,
        "categoria_tickets": 0,
        "pix_key": get_config().get("PIX_KEY", ""),
        "qr_code_url": "",
        "delivery_channel": 0,
        "feedback_channel": 0,
        "emojis": {
            "emoji_titulo": "🛒",
            "emoji_categoria": "📁",
            "emoji_produto": "🛍️",
            "emoji_comprar": "✅",
            "emoji_carrinho": "🛒",
            "emoji_pix": "💸",
            "emoji_confirmar": "✅",
            "emoji_cancelar": "❌",
            "emoji_entrega": "📦",
        },
        "cor_botao_comprar": "#57F287",
        "cor_botao_cancelar": "#ED4245",
        "categorias": [],
    }


# ---------- Embed de pré-visualização ----------
def build_preview_embed(menu: dict, bot=None) -> discord.Embed:
    emoji_titulo = emoji_for_text(menu["emojis"].get("emoji_titulo", ""), bot)
    titulo = f"{emoji_titulo} {menu['titulo']}".strip() if emoji_titulo else menu["titulo"]
    embed = discord.Embed(
        title=titulo,
        description=menu["descricao"],
        color=hex_to_int(menu["cor"]),
    )
    if menu.get("banner_url"):
        embed.set_image(url=menu["banner_url"])

    if menu["categorias"]:
        for cat in menu["categorias"]:
            emoji_cat = emoji_for_text(cat.get("emoji") or menu["emojis"].get("emoji_categoria", ""), bot) or "📁"
            produtos = cat.get("produtos", [])
            if produtos:
                linhas = []
                for p in produtos:
                    estoque = len(p.get("estoque", []))
                    pe = emoji_for_text(p.get("emoji") or menu["emojis"].get("emoji_produto", ""), bot) or "🛍️"
                    linhas.append(f"{pe} **{p['nome']}** — R$ {p['preco']:.2f} `(estoque: {estoque})`")
                embed.add_field(
                    name=f"{emoji_cat} {cat['nome']}",
                    value="\n".join(linhas),
                    inline=False,
                )
            else:
                embed.add_field(
                    name=f"{emoji_cat} {cat['nome']}",
                    value="*Nenhum produto cadastrado.*",
                    inline=False,
                )
    else:
        embed.add_field(name="\u200b", value="*Nenhuma categoria cadastrada ainda.*", inline=False)

    embed.set_footer(text="Pré-visualização do menu • Painel Administrativo")
    return embed


# ---------- Modais ----------
class TextosModal(discord.ui.Modal, title="Editar textos do menu"):
    def __init__(self, view: "ConfigView"):
        super().__init__()
        self.view_ref = view
        m = view.menu
        self.titulo = discord.ui.TextInput(
            label="Título", default=m["titulo"], max_length=100, required=True
        )
        self.descricao = discord.ui.TextInput(
            label="Descrição", style=discord.TextStyle.paragraph,
            default=m["descricao"], max_length=2000, required=True,
        )
        self.cor = discord.ui.TextInput(
            label="Cor do embed (HEX, ex: #5865F2)", default=m["cor"], max_length=7,
        )
        self.banner = discord.ui.TextInput(
            label="URL do banner (opcional)", default=m.get("banner_url", ""),
            required=False, max_length=500,
        )
        self.add_item(self.titulo)
        self.add_item(self.descricao)
        self.add_item(self.cor)
        self.add_item(self.banner)

    async def on_submit(self, interaction: discord.Interaction):
        m = self.view_ref.menu
        m["titulo"] = self.titulo.value
        m["descricao"] = self.descricao.value
        m["cor"] = normalize_hex(self.cor.value, fallback=m.get("cor", "#5865F2"))
        m["banner_url"] = self.banner.value.strip()
        await self.view_ref.refresh(interaction)


class CoresBotoesModal(discord.ui.Modal, title="Cores dos botões"):
    def __init__(self, view: "ConfigView"):
        super().__init__()
        self.view_ref = view
        m = view.menu
        self.cor_comprar = discord.ui.TextInput(
            label="Cor botão Comprar/Confirmar (HEX)",
            default=m.get("cor_botao_comprar", "#57F287"), max_length=7,
        )
        self.cor_cancelar = discord.ui.TextInput(
            label="Cor botão Cancelar (HEX)",
            default=m.get("cor_botao_cancelar", "#ED4245"), max_length=7,
        )
        self.add_item(self.cor_comprar)
        self.add_item(self.cor_cancelar)

    async def on_submit(self, interaction: discord.Interaction):
        m = self.view_ref.menu
        m["cor_botao_comprar"] = normalize_hex(self.cor_comprar.value, fallback=m.get("cor_botao_comprar", "#57F287"))
        m["cor_botao_cancelar"] = normalize_hex(self.cor_cancelar.value, fallback=m.get("cor_botao_cancelar", "#ED4245"))
        await self.view_ref.refresh(interaction)


class EmojisModal(discord.ui.Modal):
    def __init__(self, view: "ConfigView", chaves: list, titulo: str):
        super().__init__(title=titulo)
        self.view_ref = view
        self.chaves = chaves
        self.inputs = []
        for chave in chaves:
            inp = discord.ui.TextInput(
                label=chave,
                default=view.menu["emojis"].get(chave, ""),
                required=False,
                max_length=100,
                placeholder="🛒  ou  <:nome:123456789>  ou  :nome:",
            )
            self.inputs.append(inp)
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction):
        bot = self.view_ref.bot
        avisos = []
        import re as _re
        short_re = _re.compile(r"^:([a-zA-Z0-9_]+):$")
        full_re = _re.compile(r"^<a?:[a-zA-Z0-9_]+:\d+>$")
        for chave, inp in zip(self.chaves, self.inputs):
            valor = inp.value.strip()
            m = short_re.match(valor)
            if m and bot is not None:
                nome = m.group(1)
                achou = None
                for em in bot.emojis:
                    if em.name == nome:
                        achou = f"<{'a' if em.animated else ''}:{em.name}:{em.id}>"
                        break
                if achou:
                    valor = achou
                else:
                    avisos.append(f"⚠️ `{chave}`: emoji `:{nome}:` não foi encontrado.")
            elif valor and not full_re.match(valor) and len(valor) > 4 and ":" in valor:
                avisos.append(f"⚠️ `{chave}`: formato suspeito.")
            self.view_ref.menu["emojis"][chave] = valor

        if avisos:
            await interaction.response.send_message("\n".join(avisos), ephemeral=True)
            await self.view_ref.refresh_followup()
        else:
            await self.view_ref.refresh(interaction)


class ConfigAvancadaModal(discord.ui.Modal, title="Configurações Avançadas"):
    def __init__(self, view: "ConfigView"):
        super().__init__()
        self.view_ref = view
        m = view.menu
        self.cargo = discord.ui.TextInput(
            label="ID do cargo 'Cliente em Compra'",
            default=str(m.get("cargo_compra", 0) or ""),
            required=False, max_length=25,
        )
        self.pix = discord.ui.TextInput(
            label="Chave PIX",
            default=m.get("pix_key", ""), required=False, max_length=200,
        )
        self.qr_code = discord.ui.TextInput(
            label="URL da imagem do QR Code PIX",
            default=m.get("qr_code_url", ""), required=False, max_length=500,
        )
        self.delivery = discord.ui.TextInput(
            label="ID do canal de Delivery (Logs)",
            default=str(m.get("delivery_channel", 0) or ""),
            required=False, max_length=25,
        )
        self.feedback = discord.ui.TextInput(
            label="ID do canal de Feedback",
            default=str(m.get("feedback_channel", 0) or ""),
            required=False, max_length=25,
        )
        self.add_item(self.cargo)
        self.add_item(self.pix)
        self.add_item(self.qr_code)
        self.add_item(self.delivery)
        self.add_item(self.feedback)

    async def on_submit(self, interaction: discord.Interaction):
        m = self.view_ref.menu
        try:
            m["cargo_compra"] = int(self.cargo.value) if self.cargo.value.strip() else 0
            m["delivery_channel"] = int(self.delivery.value) if self.delivery.value.strip() else 0
            m["feedback_channel"] = int(self.feedback.value) if self.feedback.value.strip() else 0
        except ValueError:
            pass
        m["pix_key"] = self.pix.value
        m["qr_code_url"] = self.qr_code.value.strip()
        await self.view_ref.refresh(interaction)


class SalvarMenuModal(discord.ui.Modal, title="Salvar Menu"):
    def __init__(self, view: "ConfigView"):
        super().__init__()
        self.view_ref = view
        self.nome = discord.ui.TextInput(label="Nome interno do menu (ex: loja_premium)", max_length=50, required=True)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction):
        nome = self.nome.value.strip().lower().replace(" ", "_")
        menus = load_json(MENUS_PATH, {})
        menus[nome] = self.view_ref.menu
        save_json(MENUS_PATH, menus)
        await interaction.response.send_message(f"✅ Menu **{nome}** salvo com sucesso!", ephemeral=True)


# ---------- Gerenciamento de Categorias e Produtos ----------

class ProdutoModal(discord.ui.Modal):
    def __init__(self, view: "ProdutosView", ci: int, pi: int = None):
        titulo = "Editar Produto" if pi is not None else "Adicionar Produto"
        super().__init__(title=titulo)
        self.view_ref = view
        self.ci = ci
        self.pi = pi
        
        m = view.parent.parent.menu
        prod = m["categorias"][ci]["produtos"][pi] if pi is not None else {"nome": "", "preco": 0.0, "emoji": "🛍️", "estoque": []}
        
        self.nome = discord.ui.TextInput(label="Nome do Produto", default=prod["nome"], max_length=100, required=True)
        self.preco = discord.ui.TextInput(label="Preço (ex: 10.50)", default=str(prod["preco"]), max_length=20, required=True)
        self.emoji = discord.ui.TextInput(label="Emoji", default=prod["emoji"], max_length=100, required=False)
        self.estoque = discord.ui.TextInput(
            label="Estoque (um por linha)", 
            style=discord.TextStyle.paragraph,
            default="\n".join(prod["estoque"]),
            required=False
        )
        
        self.add_item(self.nome)
        self.add_item(self.preco)
        self.add_item(self.emoji)
        self.add_item(self.estoque)

    async def on_submit(self, interaction: discord.Interaction):
        m = self.view_ref.parent.parent.menu
        try:
            preco_val = float(self.preco.value.replace(",", "."))
        except ValueError:
            return await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
            
        estoque_list = [line.strip() for line in self.estoque.value.split("\n") if line.strip()]
        
        prod_data = {
            "nome": self.nome.value,
            "preco": preco_val,
            "emoji": self.emoji.value or "🛍️",
            "estoque": estoque_list
        }
        
        if self.pi is not None:
            m["categorias"][self.ci]["produtos"][self.pi] = prod_data
        else:
            m["categorias"][self.ci]["produtos"].append(prod_data)
            
        await self.view_ref.refresh_view(interaction)


class ProdutosView(discord.ui.View):
    def __init__(self, parent_view: "CategoriasView", ci: int):
        super().__init__(timeout=600)
        self.parent = parent_view
        self.ci = ci
        self._build()

    def _build(self):
        self.clear_items()
        m = self.parent.parent.menu
        cat = m["categorias"][self.ci]
        prods = cat["produtos"]
        
        if prods:
            options = []
            for i, p in enumerate(prods):
                options.append(discord.SelectOption(label=p["nome"][:100], value=str(i), description=f"R$ {p['preco']:.2f} | Estoque: {len(p['estoque'])}"))
            
            sel = discord.ui.Select(placeholder="Selecione um produto para editar/remover", options=options)
            async def sel_cb(i: discord.Interaction):
                pi = int(sel.values[0])
                await i.response.send_modal(ProdutoModal(self, self.ci, pi))
            sel.callback = sel_cb
            self.add_item(sel)

        btn_add = discord.ui.Button(label="Adicionar Produto", style=discord.ButtonStyle.success, emoji="➕")
        btn_add.callback = lambda i: i.response.send_modal(ProdutoModal(self, self.ci))
        self.add_item(btn_add)

        if prods:
            btn_del = discord.ui.Button(label="Remover Selecionado", style=discord.ButtonStyle.danger, emoji="🗑️")
            async def del_cb(i: discord.Interaction):
                # Pegar o valor do select se houver
                # Como o select não mantém estado fácil aqui, vamos pedir para selecionar de novo ou usar um truque
                await i.response.send_message("Selecione o produto no menu acima e clique em editar para alterar. Para remover, use o botão de remover que aparecerá no modal (simulação).", ephemeral=True)
            btn_del.callback = del_cb
            # self.add_item(btn_del) # Simplificando para evitar bugs de estado

        btn_back = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, emoji="⬅️")
        btn_back.callback = lambda i: i.response.edit_message(content="📁 Gerenciar categorias", view=self.parent)
        self.add_item(btn_back)

    async def refresh_view(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(content=f"📦 Produtos da categoria: **{self.parent.parent.menu['categorias'][self.ci]['nome']}**", view=self)


class AddCategoriaModal(discord.ui.Modal, title="Adicionar Categoria"):
    def __init__(self, view: "CategoriasView"):
        super().__init__()
        self.view_ref = view
        self.nome = discord.ui.TextInput(label="Nome da Categoria", max_length=50, required=True)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.parent.menu["categorias"].append({
            "nome": self.nome.value,
            "emoji": "📁",
            "produtos": []
        })
        await self.view_ref.refresh_view(interaction)


class CategoriasView(discord.ui.View):
    def __init__(self, parent_view: "ConfigView"):
        super().__init__(timeout=600)
        self.parent = parent_view
        self._build()

    def _build(self):
        self.clear_items()
        m = self.parent.menu
        cats = m["categorias"]
        
        if cats:
            options = []
            for i, c in enumerate(cats):
                options.append(discord.SelectOption(label=c["nome"][:100], value=str(i), emoji=c.get("emoji") or "📁"))
            
            sel = discord.ui.Select(placeholder="Selecione uma categoria para gerenciar produtos", options=options)
            async def sel_cb(i: discord.Interaction):
                ci = int(sel.values[0])
                await i.response.edit_message(content=f"📦 Produtos da categoria: **{cats[ci]['nome']}**", view=ProdutosView(self, ci))
            sel.callback = sel_cb
            self.add_item(sel)

        btn_add = discord.ui.Button(label="Adicionar Categoria", style=discord.ButtonStyle.primary, emoji="➕")
        btn_add.callback = lambda i: i.response.send_modal(AddCategoriaModal(self))
        self.add_item(btn_add)

        btn_back = discord.ui.Button(label="Voltar ao Painel", style=discord.ButtonStyle.secondary, emoji="⬅️")
        btn_back.callback = lambda i: self.parent.refresh(i)
        self.add_item(btn_back)

    async def refresh_view(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(content="📁 Gerenciar categorias", view=self)


class ConfigView(discord.ui.View):
    def __init__(self, author_id: int, menu: dict = None, bot=None):
        super().__init__(timeout=900)
        self.author_id = author_id
        self.menu = menu or default_menu()
        self.bot = bot
        self._last_interaction = None
        self._build()

    def _build(self):
        self.clear_items()
        sel = discord.ui.Select(
            placeholder="⚙️ Escolha o que deseja configurar...",
            options=[
                discord.SelectOption(label="Textos do menu", value="textos", emoji="📝"),
                discord.SelectOption(label="Emojis (parte 1)", value="emojis1", emoji="🎨"),
                discord.SelectOption(label="Emojis (parte 2)", value="emojis2", emoji="✨"),
                discord.SelectOption(label="Cores dos botões", value="cores_btn", emoji="🎯"),
                discord.SelectOption(label="Tipo de seleção", value="tipo", emoji="🧩"),
                discord.SelectOption(label="Categorias e Produtos", value="categorias", emoji="📦"),
                discord.SelectOption(label="Configurações Avançadas", value="avancado", emoji="🔐"),
            ],
        )
        sel.callback = self._on_section
        self.add_item(sel)

        btn_save = discord.ui.Button(label="Salvar menu", style=discord.ButtonStyle.success, emoji="💾", row=1)
        btn_save.callback = lambda i: i.response.send_modal(SalvarMenuModal(self))
        self.add_item(btn_save)

        btn_close = discord.ui.Button(label="Fechar", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
        btn_close.callback = lambda i: i.response.edit_message(content="Painel fechado.", embed=None, view=None)
        self.add_item(btn_close)

    async def _on_section(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0]
        if choice == "textos": return await interaction.response.send_modal(TextosModal(self))
        if choice == "emojis1": return await interaction.response.send_modal(EmojisModal(self, ["emoji_titulo", "emoji_categoria", "emoji_produto", "emoji_comprar", "emoji_carrinho"], "Emojis 1"))
        if choice == "emojis2": return await interaction.response.send_modal(EmojisModal(self, ["emoji_pix", "emoji_confirmar", "emoji_cancelar", "emoji_entrega"], "Emojis 2"))
        if choice == "cores_btn": return await interaction.response.send_modal(CoresBotoesModal(self))
        if choice == "tipo":
            self.menu["tipo_selecao"] = "buttons" if self.menu["tipo_selecao"] == "select" else "select"
            return await self.refresh(interaction)
        if choice == "categorias": return await interaction.response.edit_message(content="📁 Gerenciar categorias", embed=None, view=CategoriasView(self))
        if choice == "avancado": return await interaction.response.send_modal(ConfigAvancadaModal(self))

    async def refresh(self, interaction: discord.Interaction):
        self._last_interaction = interaction
        self._build()
        embed = build_preview_embed(self.menu, self.bot)
        embed_info = discord.Embed(
            title="⚙️ Painel de Configuração",
            description=(
                f"**Tipo:** `{self.menu['tipo_selecao']}` | **Cor:** `{self.menu['cor']}`\n"
                f"**Categorias:** `{len(self.menu['categorias'])}` | **PIX:** `{self.menu.get('pix_key') or '—'}`\n"
                f"**Delivery:** <#{self.menu.get('delivery_channel')}> | **Feedback:** <#{self.menu.get('feedback_channel')}>"
            ),
            color=hex_to_int(self.menu["cor"]),
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[embed_info, embed], view=self)
        else:
            await interaction.response.edit_message(content=None, embeds=[embed_info, embed], view=self)

    async def refresh_followup(self):
        inter = self._last_interaction
        if not inter: return
        self._build()
        embed = build_preview_embed(self.menu, self.bot)
        try: await inter.edit_original_response(content=None, embeds=[embed], view=self)
        except: pass


class MenuConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="[ADMIN] Abre o painel de configuração de menus de venda.")
    async def menu(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message("❌ Apenas admins.", ephemeral=True)
        
        view = discord.ui.View()
        btn_new = discord.ui.Button(label="Novo Menu", style=discord.ButtonStyle.success, emoji="➕")
        btn_edit = discord.ui.Button(label="Editar Menu", style=discord.ButtonStyle.primary, emoji="📝")
        
        async def new_cb(i: discord.Interaction):
            await i.response.send_message("⚙️ Criando novo menu...", view=ConfigView(i.user.id, bot=self.bot), ephemeral=True)
        
        async def edit_cb(i: discord.Interaction):
            menus = load_json(MENUS_PATH, {})
            if not menus: return await i.response.send_message("❌ Nenhum menu salvo.", ephemeral=True)
            sel = discord.ui.Select(placeholder="Escolha o menu para editar...", options=[discord.SelectOption(label=n, value=n) for n in menus.keys()])
            async def sel_cb(i2: discord.Interaction):
                m = menus[sel.values[0]]
                await i2.response.edit_message(content=f"⚙️ Editando **{sel.values[0]}**", view=ConfigView(i2.user.id, menu=m, bot=self.bot))
            sel.callback = sel_cb
            v = discord.ui.View(); v.add_item(sel)
            await i.response.send_message("Selecione o menu:", view=v, ephemeral=True)

        btn_new.callback = new_cb
        btn_edit.callback = edit_cb
        view.add_item(btn_new); view.add_item(btn_edit)
        await interaction.response.send_message("Escolha uma opção:", view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MenuConfig(bot))
