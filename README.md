# 🛒 Bot de Vendas Discord

Bot completo de vendas para Discord com painel administrativo, sistema de tickets, PIX e gerenciamento de produtos.

## 📋 Requisitos
- Python 3.10+
- discord.py 2.3+

## ⚙️ Instalação
```bash
pip install -r requirements.txt
```

## 🔧 Configuração

Edite o arquivo `config.json`:

```json
{
    "TOKEN": "SEU_TOKEN_DO_BOT",
    "OWNER_ID": 123456789012345678,
    "ADMINS": [],
    "PIX_KEY": "sua-chave-pix@email.com"
}
```

- **TOKEN**: Token do seu bot (https://discord.com/developers/applications)
- **OWNER_ID**: Seu ID do Discord (clique direito no seu nome > Copiar ID)
- **ADMINS**: Lista de IDs que podem usar o painel `/menu`
- **PIX_KEY**: Sua chave PIX padrão (pode ser alterada por menu também)

## ▶️ Como Rodar
```bash
python main.py
```

## 🎯 Comandos

| Comando | Quem usa | Descrição |
|---------|----------|-----------|
| `/perm` | Owner | Adiciona/remove admins |
| `/menu` | Admins | Abre o painel de configuração |
| `/set` | Admins | Envia um menu salvo no canal |
| `/cancelar` | Admins | Cancela um ticket manualmente |

## 🎨 Emojis Customizados

Você pode configurar emojis customizados nos seguintes locais (use o formato `<:nome:id>` ou apenas o emoji unicode):

- `emoji_titulo` — Aparece no título do menu
- `emoji_categoria` — Aparece nas categorias
- `emoji_produto` — Aparece nos produtos
- `emoji_comprar` — Botão de comprar
- `emoji_carrinho` — Embed do ticket
- `emoji_pix` — Embed do PIX
- `emoji_confirmar` — Botão confirmar
- `emoji_cancelar` — Botão cancelar
- `emoji_entrega` — Embed de entrega na DM

## 🔁 Fluxo de Compra

1. Usuário clica no menu/botão e escolhe um produto.
2. Bot abre um ticket privado.
3. Embed de confirmação do pedido (Confirmar/Cancelar).
4. Ao confirmar → mostra PIX + botão "Confirmar Pagamento" (só admins/cargo).
5. Admin confirma → produto é enviado na DM, cargo removido, ticket fechado.

## 💾 Persistência
Tudo é salvo em `data/menus.json` e `data/tickets.json`. Faça backup desses arquivos.

## 🎨 Emojis customizados — IMPORTANTE

Para usar emojis personalizados do seu servidor nos embeds e botões, você tem 3 formas:

1. **Emoji unicode** (mais simples): cole direto, ex: `🛒` `📁` `✅`
2. **Formato completo `<:nome:ID>`** (recomendado): no chat do Discord digite `\:nome_do_emoji:` (com a barra invertida) e dê enter — o Discord vai mostrar o código completo `<:nome:1234567890>`. Copie e cole no campo.
3. **Formato curto `:nome:`**: o bot vai tentar resolver automaticamente buscando esse emoji nos servidores onde ele está. Se ele não encontrar, vai te avisar.

⚠️ **Importante**: o bot precisa estar em um servidor que tenha o emoji para conseguir exibi-lo. Se você colocar `:emoji_1:` e o bot não estiver em nenhum servidor com um emoji chamado `emoji_1`, ele vai aparecer em branco (não como `:emoji_1:` literal).

## 🎨 Cor da lateral do embed

A cor azul/roxa que aparece na lateral do embed é controlada pelo campo **"Cor do embed (HEX)"** no modal `Textos do menu`. Coloque qualquer cor HEX (com ou sem `#`), exemplos:

- `#FF0000` → vermelho
- `#00FF00` → verde
- `#FFD700` → dourado
- `#5865F2` → azul Discord (padrão)
- `#9B59B6` → roxo

Depois de alterar, o painel mostra a pré-visualização atualizada e ao usar `/set` o embed publicado fica com a nova cor.
