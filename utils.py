"""Funções utilitárias para o bot de vendas."""
import json
import os
import re
from typing import Any, Optional

CONFIG_PATH = "config.json"
MENUS_PATH = "data/menus.json"
TICKETS_PATH = "data/tickets.json"


def load_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default if default is not None else {}


def save_json(path: str, data: Any) -> None:
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_config() -> dict:
    return load_json(CONFIG_PATH, {})


def save_config(config: dict) -> None:
    save_json(CONFIG_PATH, config)


def is_owner(user_id: int) -> bool:
    return user_id == get_config().get("OWNER_ID")


def is_admin(user_id: int) -> bool:
    config = get_config()
    return user_id == config.get("OWNER_ID") or user_id in config.get("ADMINS", [])


def hex_to_int(hex_color: str) -> int:
    """Converte HEX (#RRGGBB) em int para usar em embeds.
    Aceita formatos: #RRGGBB, RRGGBB, 0xRRGGBB."""
    if not hex_color:
        return 0x5865F2
    h = str(hex_color).strip().lstrip("#").lstrip("0x").lstrip("0X")
    # remove espaços e caracteres inválidos
    h = re.sub(r"[^0-9a-fA-F]", "", h)
    if len(h) == 3:  # formato curto #RGB → #RRGGBB
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return 0x5865F2
    try:
        return int(h, 16)
    except ValueError:
        return 0x5865F2


def normalize_hex(hex_color: str, fallback: str = "#5865F2") -> str:
    """Normaliza string HEX para o formato #RRGGBB."""
    if not hex_color:
        return fallback
    h = str(hex_color).strip().lstrip("#").lstrip("0x").lstrip("0X")
    h = re.sub(r"[^0-9a-fA-F]", "", h)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return fallback
    return f"#{h.upper()}"


def hex_to_button_style(hex_color: str):
    """Mapeia uma cor HEX para o ButtonStyle mais próximo do Discord."""
    import discord
    if not hex_color:
        return discord.ButtonStyle.primary
    h = str(hex_color).lstrip("#").lower()
    mapping = {
        "5865f2": discord.ButtonStyle.primary,
        "57f287": discord.ButtonStyle.success,
        "ed4245": discord.ButtonStyle.danger,
        "4f545c": discord.ButtonStyle.secondary,
    }
    if h in mapping:
        return mapping[h]
    try:
        r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    except (ValueError, IndexError):
        return discord.ButtonStyle.primary
    if g > r and g > b:
        return discord.ButtonStyle.success
    if r > g and r > b:
        return discord.ButtonStyle.danger
    if abs(r - g) < 30 and abs(g - b) < 30 and r < 120:
        return discord.ButtonStyle.secondary
    return discord.ButtonStyle.primary


# Regex para detectar emojis customizados completos
_CUSTOM_EMOJI_RE = re.compile(r"^<a?:[a-zA-Z0-9_]+:\d+>$")
# Regex para detectar formato curto :nome: (que NÃO funciona em embeds)
_SHORT_EMOJI_RE = re.compile(r"^:([a-zA-Z0-9_]+):$")


def parse_emoji(emoji_str: str, bot=None) -> Optional[str]:
    """Aceita unicode ou <:nome:id> / <a:nome:id>.
    Se receber :nome: (formato curto), tenta resolver pelo cache do bot.
    Retorna string utilizável por SelectOption / Button, ou None se inválido.
    """
    if not emoji_str:
        return None
    s = emoji_str.strip()
    if not s:
        return None

    # Já está no formato completo <:nome:ID> ou <a:nome:ID>
    if _CUSTOM_EMOJI_RE.match(s):
        return s

    # Formato curto :nome: → tenta resolver via cache do bot
    short = _SHORT_EMOJI_RE.match(s)
    if short and bot is not None:
        nome = short.group(1)
        try:
            for em in bot.emojis:
                if em.name == nome:
                    return f"<{'a' if em.animated else ''}:{em.name}:{em.id}>"
        except Exception:
            pass
        # Não achou — retorna None (melhor não exibir do que mostrar :nome: literal)
        return None

    if short and bot is None:
        # Sem bot disponível, não conseguimos resolver — retorna None
        return None

    # Provavelmente unicode (🛒, 📁, etc.) — retorna como veio
    return s


def emoji_for_text(emoji_str: str, bot=None) -> str:
    """Versão para uso em texto de embed. Resolve :nome: via cache do bot.
    Sempre retorna string (vazia se não conseguir resolver)."""
    if not emoji_str:
        return ""
    s = emoji_str.strip()
    if not s:
        return ""
    if _CUSTOM_EMOJI_RE.match(s):
        return s
    short = _SHORT_EMOJI_RE.match(s)
    if short and bot is not None:
        nome = short.group(1)
        try:
            for em in bot.emojis:
                if em.name == nome:
                    return f"<{'a' if em.animated else ''}:{em.name}:{em.id}>"
        except Exception:
            pass
        return ""  # evita mostrar :nome: literal no embed
    if short:
        return ""
    return s
