"""Cog: /menu — painel de configuração do menu de vendas.

Estrutura de um "menu" salvo em data/menus.json:
{
    "nome_do_menu": {
        "titulo": "...",
        "descricao": "...",
        "cor": "#5865F2",
        "banner_url": "",
        "tipo_selecao": "select" | "buttons",
        "cargo_compra": 123,            # ID do cargo "Cliente em Compra"
        "categoria_tickets": 0,         # opcional: ID da categoria onde tickets serão criados
        "pix_key": "...",
        "emojis": {
            "emoji_titulo": "🛒",
            "emoji_categoria": "📁",
            "emoji_produto": "🛍️",
            "emoji_comprar": "✅",
            "emoji_carrinho": "🛒",
            "emoji_pix": "💸",
            "emoji_confirmar": "✅",
            "emoji_cancelar": "❌",
            "emoji_entrega": "📦"
        },
        "cor_botao_comprar": "#57F287",
        "cor_botao_cancelar": "#ED4245",
        "categorias": [
            {
                "nome": "Categoria 1",
                "emoji": "📁",
                "produtos": [
                    {
                        "nome": "Produto X",
                        "descricao": "...",
                        "preco": 9.99,
                        "emoji": "🛍️",
                        "estoque": ["chave1", "chave2"]   # lista de chaves/itens
                    }
                ]
            }
        ]
    }
}
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
    """Modal para editar emojis. IMPORTANTE: para emojis customizados,
    use o formato completo `<:nome:ID>` (digite `\\:nome:` no Discord
    e copie o resultado), OU apenas `:nome:` se o emoji estiver num
    servidor onde o bot está presente (ele será resolvido automaticamente).
    """
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
            # Tenta converter formato curto :nome: para formato completo via cache do bot
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
                    avisos.append(f"⚠️ `{chave}`: emoji `:{nome}:` não foi encontrado em nenhum servidor onde o bot está. "
                                  f"Use o formato `<:{nome}:ID>` ou adicione o bot ao servidor onde o emoji existe.")
            elif valor and not full_re.match(valor) and len(valor) > 4 and ":" in valor:
                avisos.append(f"⚠️ `{chave}`: formato suspeito. Use unicode (🛒) ou `<:nome:ID>`.")
            self.view_ref.menu["emojis"][chave] = valor

        if avisos:
            await interaction.response.send_message("\n".join(avisos), ephemeral=True)
            await self.view_ref.refresh_followup()
        else:
            await self.view_ref.refresh(interaction)


class CargoPixModal(discord.ui.Modal, title="Cargo de compra e PIX"):
    def __init__(self, view: "ConfigView"):
        super().__init__()
        self.view_ref = view
        m = view.menu
        self.cargo = discord.ui.TextInput(
            label="ID do cargo 'Cliente em Compra'",
            default=str(m.get("cargo_compra", 0) or ""),
            required=False, max_length=25,
        )
        self.categoria = discord.ui.TextInput(
            label="ID da categoria de tickets (opcional)",
            default=str(m.get("categoria_tickets", 0) or ""),
            required=False, max_length=25,
        )
        self.pix = discord.ui.TextInput(
            label="Chave PIX",
            default=m.get("pix_key", ""), required=False, max_length=200,
        )
        self.add_item(self.cargo)
        self.add_item(self.categoria)
        self.add_item(self.pix)

    async def on_submit(self, interaction: discord.Interaction):
        m = self.view_ref.menu
        try:
            m["cargo_compra"] = int(self.cargo.value) if self.cargo.value.strip() else 0
        except ValueError:
            m["cargo_compra"] = 0
        try:
            m["categoria_tickets"] = int(self.categoria.value) if self.categoria.value.strip() else 0
        except ValueError:
            m["categoria_tickets"] = 0
        m["pix_key"] = self.pix.value.strip()
        await self.view_ref.refresh(interaction)


# ---------- Categorias / Produtos ----------
class CategoriaModal(discord.ui.Modal, title="Adicionar / Editar Categoria"):
    def __init__(self, view: "ConfigView", index: int = -1):
        super().__init__()
        self.view_ref = view
        self.index = index
        cat = view.menu["categorias"][index] if index >= 0 else {"nome": "", "emoji": ""}
        self.nome = discord.ui.TextInput(label="Nome da categoria", default=cat.get("nome", ""), max_length=80)
        self.emoji = discord.ui.TextInput(label="Emoji da categoria", default=cat.get("emoji", ""),
                                          required=False, max_length=100)
        self.add_item(self.nome)
        self.add_item(self.emoji)

    async def on_submit(self, interaction: discord.Interaction):
        if self.index >= 0:
            self.view_ref.menu["categorias"][self.index]["nome"] = self.nome.value
            self.view_ref.menu["categorias"][self.index]["emoji"] = self.emoji.value
        else:
            self.view_ref.menu["categorias"].append({
                "nome": self.nome.value, "emoji": self.emoji.value, "produtos": [],
            })
        await self.view_ref.refresh(interaction)


class ProdutoModal(discord.ui.Modal, title="Adicionar / Editar Produto"):
    def __init__(self, view: "ConfigView", cat_index: int, prod_index: int = -1):
        super().__init__()
        self.view_ref = view
        self.cat_index = cat_index
        self.prod_index = prod_index
        cat = view.menu["categorias"][cat_index]
        prod = cat["produtos"][prod_index] if prod_index >= 0 else {
            "nome": "", "descricao": "", "preco": 0.0, "emoji": "", "estoque": []
        }
        self.nome = discord.ui.TextInput(label="Nome", default=prod["nome"], max_length=80)
        self.descricao = discord.ui.TextInput(
            label="Descrição", style=discord.TextStyle.paragraph,
            default=prod["descricao"], max_length=500, required=False,
        )
        self.preco = discord.ui.TextInput(label="Preço (ex: 9.99)", default=str(prod["preco"]), max_length=15)
        self.emoji = discord.ui.TextInput(label="Emoji", default=prod.get("emoji", ""),
                                          required=False, max_length=100)
        self.estoque = discord.ui.TextInput(
            label="Estoque (separado por vírgula)",
            style=discord.TextStyle.paragraph,
            default=", ".join(prod.get("estoque", [])),
            required=False, max_length=2000,
            placeholder="chave1, chave2, conta:senha, ...",
        )
        for i in (self.nome, self.descricao, self.preco, self.emoji, self.estoque):
            self.add_item(i)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            preco = float(self.preco.value.replace(",", "."))
        except ValueError:
            return await interaction.response.send_message(
                "❌ Preço inválido. Use um número como `9.99`.", ephemeral=True
            )

        estoque_lista = [s.strip() for s in self.estoque.value.split(",") if s.strip()]
        novo = {
            "nome": self.nome.value,
            "descricao": self.descricao.value,
            "preco": preco,
            "emoji": self.emoji.value,
            "estoque": estoque_lista,
        }
        cat = self.view_ref.menu["categorias"][self.cat_index]
        if self.prod_index >= 0:
            cat["produtos"][self.prod_index] = novo
        else:
            cat["produtos"].append(novo)
        await self.view_ref.refresh(interaction)


class SalvarMenuModal(discord.ui.Modal, title="Salvar menu"):
    def __init__(self, view: "ConfigView"):
        super().__init__()
        self.view_ref = view
        self.nome = discord.ui.TextInput(
            label="Nome para salvar este menu",
            placeholder="ex: loja-principal",
            max_length=60,
        )
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction):
        nome = self.nome.value.strip()
        if not nome:
            return await interaction.response.send_message("❌ Nome inválido.", ephemeral=True)
        menus = load_json(MENUS_PATH, {})
        menus[nome] = self.view_ref.menu
        save_json(MENUS_PATH, menus)
        await interaction.response.send_message(
            f"✅ Menu **{nome}** salvo com sucesso! Use `/set` para enviá-lo num canal.",
            ephemeral=True,
        )


# ---------- Sub-views (gerenciamento de categorias/produtos) ----------
class CategoriasView(discord.ui.View):
    def __init__(self, parent: "ConfigView"):
        super().__init__(timeout=600)
        self.parent = parent
        self._build()

    def _build(self):
        self.clear_items()
        cats = self.parent.menu["categorias"]
        if cats:
            options = []
            for i, c in enumerate(cats):
                options.append(discord.SelectOption(
                    label=c["nome"][:90] or f"Categoria {i+1}",
                    value=str(i),
                    emoji=parse_emoji(c.get("emoji")) or "📁",
                    description=f"{len(c.get('produtos', []))} produto(s)",
                ))
            select = discord.ui.Select(placeholder="Editar categoria...", options=options)
            async def edit_cb(interaction: discord.Interaction):
                idx = int(select.values[0])
                view = ProdutosView(self.parent, idx)
                await interaction.response.edit_message(
                    content=f"📁 Editando categoria **{cats[idx]['nome']}**",
                    embed=None, view=view,
                )
            select.callback = edit_cb
            self.add_item(select)

        self.add_item(self._btn_add_cat())
        if cats:
            self.add_item(self._btn_del_cat())
        self.add_item(self._btn_voltar())

    def _btn_add_cat(self):
        btn = discord.ui.Button(label="Nova categoria", style=discord.ButtonStyle.success, emoji="➕")
        async def cb(interaction: discord.Interaction):
            await interaction.response.send_modal(CategoriaModal(self.parent))
        btn.callback = cb
        return btn

    def _btn_del_cat(self):
        cats = self.parent.menu["categorias"]
        options = [
            discord.SelectOption(label=c["nome"][:90] or f"Categoria {i+1}", value=str(i))
            for i, c in enumerate(cats)
        ]
        sel = discord.ui.Select(placeholder="🗑️ Apagar categoria...", options=options)
        async def cb(interaction: discord.Interaction):
            idx = int(sel.values[0])
            cats.pop(idx)
            await self.parent.refresh(interaction)
        sel.callback = cb
        return sel

    def _btn_voltar(self):
        btn = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def cb(interaction: discord.Interaction):
            await self.parent.refresh(interaction)
        btn.callback = cb
        return btn


class ProdutosView(discord.ui.View):
    def __init__(self, parent: "ConfigView", cat_index: int):
        super().__init__(timeout=600)
        self.parent = parent
        self.cat_index = cat_index
        self._build()

    def _build(self):
        self.clear_items()
        cat = self.parent.menu["categorias"][self.cat_index]
        prods = cat.get("produtos", [])
        if prods:
            options = []
            for i, p in enumerate(prods):
                options.append(discord.SelectOption(
                    label=p["nome"][:90],
                    value=str(i),
                    emoji=parse_emoji(p.get("emoji")) or "🛍️",
                    description=f"R$ {p['preco']:.2f} • estoque: {len(p.get('estoque', []))}",
                ))
            sel = discord.ui.Select(placeholder="Editar produto...", options=options)
            async def cb(interaction: discord.Interaction):
                idx = int(sel.values[0])
                await interaction.response.send_modal(ProdutoModal(self.parent, self.cat_index, idx))
            sel.callback = cb
            self.add_item(sel)

        # botão adicionar
        btn_add = discord.ui.Button(label="Novo produto", style=discord.ButtonStyle.success, emoji="➕")
        async def add_cb(interaction: discord.Interaction):
            await interaction.response.send_modal(ProdutoModal(self.parent, self.cat_index))
        btn_add.callback = add_cb
        self.add_item(btn_add)

        # apagar produto
        if prods:
            sel_del = discord.ui.Select(
                placeholder="🗑️ Apagar produto...",
                options=[discord.SelectOption(label=p["nome"][:90], value=str(i))
                         for i, p in enumerate(prods)],
            )
            async def del_cb(interaction: discord.Interaction):
                idx = int(sel_del.values[0])
                cat["produtos"].pop(idx)
                view = ProdutosView(self.parent, self.cat_index)
                await interaction.response.edit_message(
                    content=f"📁 Editando categoria **{cat['nome']}**", embed=None, view=view,
                )
            sel_del.callback = del_cb
            self.add_item(sel_del)

        # voltar
        btn_back = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_cb(interaction: discord.Interaction):
            view = CategoriasView(self.parent)
            await interaction.response.edit_message(
                content="📁 Gerenciar categorias", embed=None, view=view,
            )
        btn_back.callback = back_cb
        self.add_item(btn_back)


# ---------- View principal de configuração ----------
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
        # Select principal de seções
        sel = discord.ui.Select(
            placeholder="⚙️ Escolha o que deseja configurar...",
            options=[
                discord.SelectOption(label="Textos do menu", value="textos",
                                     description="Título, descrição, cor e banner", emoji="📝"),
                discord.SelectOption(label="Emojis (parte 1)", value="emojis1",
                                     description="titulo, categoria, produto, comprar, carrinho", emoji="🎨"),
                discord.SelectOption(label="Emojis (parte 2)", value="emojis2",
                                     description="pix, confirmar, cancelar, entrega", emoji="✨"),
                discord.SelectOption(label="Cores dos botões", value="cores_btn",
                                     description="HEX para botões Comprar e Cancelar", emoji="🎯"),
                discord.SelectOption(label="Tipo de seleção", value="tipo",
                                     description="Select Menu ou Botões normais", emoji="🧩"),
                discord.SelectOption(label="Categorias e Produtos", value="categorias",
                                     description="Criar / editar / apagar", emoji="📦"),
                discord.SelectOption(label="Cargo de compra & PIX", value="cargo",
                                     description="Cargo Cliente em Compra, categoria, chave PIX", emoji="🔐"),
            ],
        )
        sel.callback = self._on_section
        self.add_item(sel)

        # Botão Salvar
        btn_save = discord.ui.Button(label="Salvar menu", style=discord.ButtonStyle.success, emoji="💾", row=1)
        async def save_cb(interaction: discord.Interaction):
            if not self.menu["categorias"]:
                return await interaction.response.send_message(
                    "⚠️ Adicione ao menos uma categoria antes de salvar.", ephemeral=True
                )
            await interaction.response.send_modal(SalvarMenuModal(self))
        btn_save.callback = save_cb
        self.add_item(btn_save)

        # Botão fechar
        btn_close = discord.ui.Button(label="Fechar", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
        async def close_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(content="Painel fechado.", embed=None, view=None)
        btn_close.callback = close_cb
        self.add_item(btn_close)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not is_admin(interaction.user.id):
            await interaction.response.send_message("❌ Este painel não é seu.", ephemeral=True)
            return False
        return True

    async def _on_section(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0]
        if choice == "textos":
            return await interaction.response.send_modal(TextosModal(self))
        if choice == "emojis1":
            return await interaction.response.send_modal(EmojisModal(
                self,
                ["emoji_titulo", "emoji_categoria", "emoji_produto", "emoji_comprar", "emoji_carrinho"],
                "Emojis (parte 1/2)",
            ))
        if choice == "emojis2":
            return await interaction.response.send_modal(EmojisModal(
                self,
                ["emoji_pix", "emoji_confirmar", "emoji_cancelar", "emoji_entrega"],
                "Emojis (parte 2/2)",
            ))
        if choice == "cores_btn":
            return await interaction.response.send_modal(CoresBotoesModal(self))
        if choice == "tipo":
            self.menu["tipo_selecao"] = "buttons" if self.menu["tipo_selecao"] == "select" else "select"
            return await self.refresh(interaction)
        if choice == "categorias":
            view = CategoriasView(self)
            return await interaction.response.edit_message(
                content="📁 Gerenciar categorias", embed=None, view=view,
            )
        if choice == "cargo":
            return await interaction.response.send_modal(CargoPixModal(self))

    async def refresh(self, interaction: discord.Interaction):
        self._last_interaction = interaction
        self._build()
        embed = build_preview_embed(self.menu, self.bot)
        embed_info = discord.Embed(
            title="⚙️ Painel de Configuração",
            description=(
                f"**Tipo de seleção:** `{self.menu['tipo_selecao']}`\n"
                f"**Cor embed:** `{self.menu['cor']}`\n"
                f"**Categorias:** `{len(self.menu['categorias'])}`\n"
                f"**Cargo compra:** {'<@&' + str(self.menu['cargo_compra']) + '>' if self.menu['cargo_compra'] else '*não definido*'}\n"
                f"**PIX:** `{self.menu.get('pix_key') or '—'}`"
            ),
            color=hex_to_int(self.menu["cor"]),
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embeds=[embed_info, embed], view=self)
        else:
            await interaction.response.edit_message(content=None, embeds=[embed_info, embed], view=self)

    async def refresh_followup(self):
        """Atualiza o painel original quando já enviamos uma mensagem ephemeral de aviso."""
        inter = self._last_interaction
        if not inter:
            return
        self._build()
        embed = build_preview_embed(self.menu, self.bot)
        embed_info = discord.Embed(
            title="⚙️ Painel de Configuração",
            description=(
                f"**Tipo de seleção:** `{self.menu['tipo_selecao']}`\n"
                f"**Cor embed:** `{self.menu['cor']}`\n"
                f"**Categorias:** `{len(self.menu['categorias'])}`\n"
                f"**Cargo compra:** {'<@&' + str(self.menu['cargo_compra']) + '>' if self.menu['cargo_compra'] else '*não definido*'}\n"
                f"**PIX:** `{self.menu.get('pix_key') or '—'}`"
            ),
            color=hex_to_int(self.menu["cor"]),
        )
        try:
            await inter.edit_original_response(content=None, embeds=[embed_info, embed], view=self)
        except Exception:
            pass


# ---------- Cog ----------
class MenuConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="[ADMIN] Abre o painel de configuração de menus de venda.")
    async def menu(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Apenas admins podem usar este painel.", ephemeral=True
            )
        view = ConfigView(interaction.user.id, bot=self.bot)
        view._last_interaction = interaction
        embed_info = discord.Embed(
            title="⚙️ Painel de Configuração",
            description="Use o menu abaixo para configurar seu menu de vendas.\n"
                        "Quando terminar, clique em **Salvar menu**.\n\n"
                        "💡 **Dica de emojis customizados:** digite `\\:emoji:` no chat do "
                        "Discord, copie o resultado (`<:nome:ID>`) e cole no campo de emoji.",
            color=0x5865F2,
        )
        await interaction.response.send_message(
            embeds=[embed_info, build_preview_embed(view.menu, self.bot)],
            view=view, ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MenuConfig(bot))
