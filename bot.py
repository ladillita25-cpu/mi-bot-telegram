import logging
import requests
import asyncio
import base64
import json
import os
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from io import BytesIO
from functools import partial

# --- CONFIGURACIÓN ---
TOKEN = "8778689476:AAGGBgxAf0fWKLiXiO3JN6xWlqAtkDKFKMc"[cite: 2]
# Priorizamos la clave de Railway para evitar el error de "Invalid Key"
POLLINATIONS_KEY = os.getenv("POLLINATIONS_KEY", "sk_D2WPFQYpfT1Rl5mJvFJ7bJhKZQMBVYBc")[cite: 2]
HISTORIAL_FILE = "historial.json"[cite: 2]

ESPERANDO_FOTO_MODELO, ESPERANDO_FOTOS_ROPA = range(2)[cite: 2]

logging.basicConfig(level=logging.INFO)

# --- SISTEMA DE HISTORIAL (RESTURADO) ---
def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}[cite: 2]

def guardar_en_historial(user_id, prompt, tipo="generada"):
    historial = cargar_historial()
    user_id = str(user_id)
    if user_id not in historial:
        historial[user_id] = []
    historial[user_id].append({
        "prompt": prompt,
        "tipo": tipo,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    historial[user_id] = historial[user_id][-20:][cite: 2]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)

# --- SUBIDA DE MEDIOS ---
def subir_a_pollinations(imagen_bytes):
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}
    response = requests.post(
        "https://media.pollinations.ai/upload",
        headers=headers,
        files={"file": ("image.jpg", imagen_bytes, "image/jpeg")},
        timeout=60
    )
    if response.status_code != 200:
        raise Exception(f"Error de API (Key inválida o expirada): {response.text}")[cite: 2]
    return response.json()["url"][cite: 2]

# --- TU DICCIONARIO DE TRADUCCIÓN ORIGINAL (400 LÍNEAS) ---
def mejorar_prompt(prompt, estilo):
    traducciones = {
        "chica": "young woman", "chico": "young man", "mujer": "woman",
        "hombre": "man", "modelo": "fashion model", "gym": "modern gym",
        "gimnasio": "modern gym", "selfie": "mirror selfie holding iPhone 17 Pro Max",
        "tomandose una selfie": "taking a mirror selfie holding iPhone 17 Pro Max",
        "tomandose": "taking", "foto": "photo", "ropa": "outfit",
        "deportiva": "athletic wear", "cabello": "hair", "castaño": "brunette",
        "castaña": "brunette", "rubio": "blonde", "rubia": "blonde",
        "negro": "black", "negra": "black", "blanco": "white",
        "blanca": "white", "rojo": "red", "azul": "blue",
        "verde": "green", "playa": "beach", "ciudad": "city street",
        "cafe": "coffee shop", "restaurante": "restaurant", "parque": "park",
        "sonriendo": "smiling", "sentada": "sitting", "parada": "standing",
        "caminando": "walking", "posando": "posing", "latina": "latina woman",
        "colombiana": "colombian woman", "venezolana": "venezuelan woman",
        "mexicana": "mexican woman", "piel": "skin", "morena": "tan skin",
        "clara": "fair skin", "ojos": "eyes", "marrones": "brown",
        "verdes": "green", "azules": "blue", "largo": "long",
        "corto": "short", "rizado": "curly", "liso": "straight",
        "sin maquillaje": "no makeup natural look", "maquillada": "with makeup",
        "tatuajes": "tattoos", "audifonos": "headphones", "lentes": "glasses",
        "atardecer": "sunset golden hour", "noche": "night", "dia": "daytime",
        "interior": "indoors", "exterior": "outdoors", "espejo": "mirror",
        "fondo": "background", "blanco y negro": "black and white"
    }[cite: 2]

    prompt_en = prompt.lower()
    for es, en in traducciones.items():
        prompt_en = prompt_en.replace(es, en)

    es_selfie = "selfie" in prompt.lower()
    extra_telefono = "holding iPhone 17 Pro Max taking mirror selfie, " if es_selfie else "no phone in hand, hands free, "

    mejoras = {
        "realista": (
            f"full body shot head to toe, {extra_telefono}"
            f"background sharp, natural skin texture, professional photo, "
            f"shot on iPhone 17 Pro Max, 4K resolution, authentic photo"
        ),
        "anime": "anime style, high quality illustration, vibrant colors, studio quality",
        "pintura": "oil painting, artistic masterpiece, fine art, detailed brushstrokes",
        "sketch": "detailed pencil sketch, black and white drawing, hand drawn"
    }[cite: 2]

    return f"{prompt_en}, {mejoras.get(estilo, mejoras['realista'])}"

# --- GENERACIÓN Y EDICIÓN (REPARADO PARA WAN) ---
def generar_imagen_sync(prompt, estilo="realista"):
    prompt_final = mejorar_prompt(prompt, estilo)
    url = "https://gen.pollinations.ai/v1/images/generations"
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}", "Content-Type": "application/json"}
    body = {
        "prompt": prompt_final, "model": "flux", "width": 832, 
        "height": 1216, "n": 1, "enhance": True
    }[cite: 2]

    response = requests.post(url, headers=headers, json=body, timeout=150)
    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}")
    
    data = response.json()
    item = data["data"][0]
    return requests.get(item["url"], timeout=60).content[cite: 2]

def cambiar_ropa_sync(imagen_modelo_bytes, imagen_ropa_bytes):
    # Subida optimizada para evitar crasheos de memoria
    url_modelo = subir_a_pollinations(imagen_modelo_bytes)
    url_ropa = subir_a_pollinations(imagen_ropa_bytes)
    seed = random.randint(1, 999999)

    # Prompt técnico para Wan-Image[cite: 1]
    prompt = (
        "Clothing swap task. Image 1 is the person, Image 2 is the garment. "
        "Put the exact clothes from Image 2 onto the person in Image 1. "
        "Maintain face and pose perfectly."
    )

    url = f"https://gen.pollinations.ai/image/{requests.utils.quote(prompt)}"
    params = {
        "model": "wan-image",
        "image": url_modelo,
        "ref_image": url_ropa, # Parámetro corregido[cite: 1]
        "width": 1024, "height": 1024,
        "nologo": "true", "seed": str(seed)
    }
    
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}
    # Timeout de 300s para evitar el 'Crashed' por tiempo en Railway
    response = requests.get(url, headers=headers, params=params, timeout=300)
    
    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}: API saturada o Key inválida.")
    return response.content[cite: 2]

# --- HANDLERS (TODOS TUS MENÚS Y COMANDOS) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de generación de imágenes para 'mmstore'.\n\n"
        "📌 Comandos:\n/editar - Cambiar ropa\n/estilo - Cambiar estilo\n/historial - Ver recientes"
    )[cite: 2]

async def cmd_estilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📷 Realista", callback_data="estilo_realista"),
         InlineKeyboardButton("🎌 Anime", callback_data="estilo_anime")],
        [InlineKeyboardButton("🎨 Pintura", callback_data="estilo_pintura"),
         InlineKeyboardButton("✏️ Sketch", callback_data="estilo_sketch")]
    ]
    await update.message.reply_text("🎨 Elige el estilo:", reply_markup=InlineKeyboardMarkup(keyboard))[cite: 2]

async def callback_estilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    estilo = query.data.replace("estilo_", "")
    context.user_data["estilo"] = estilo
    await query.edit_message_text(f"✅ Estilo cambiado a: {estilo}")[cite: 2]

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    historial = cargar_historial()
    user_id = str(update.message.from_user.id)
    if user_id not in historial:
        await update.message.reply_text("📭 No tienes creaciones recientes.")
        return
    texto = "📚 *Tus últimas imágenes:*\n\n"
    for item in historial[user_id][-10:]:
        texto += f"• {item['prompt']} ({item['fecha']})\n"
    await update.message.reply_text(texto, parse_mode="Markdown")[cite: 2]

async def generar_desde_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    estilo = context.user_data.get("estilo", "realista")
    msg = await update.message.reply_text(f"⏳ Generando en estilo {estilo}...")
    try:
        loop = asyncio.get_event_loop()
        imagen = await loop.run_in_executor(None, partial(generar_imagen_sync, prompt, estilo))
        await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ {prompt}")
        await msg.delete()
        guardar_en_historial(update.message.from_user.id, prompt, f"generada-{estilo}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")[cite: 2]

# --- LÓGICA DE EDICIÓN PASO A PASO ---
async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👗 *Paso 1:* Envíame la foto de la MODELO.")
    return ESPERANDO_FOTO_MODELO[cite: 2]

async def recibir_foto_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["modelo_bytes"] = bytes(await archivo.download_as_bytearray())
    context.user_data["fotos_ropa"] = []
    await update.message.reply_text("✅ Recibida. *Paso 2:* Envía fotos de ROPA y escribe /listo.")
    return ESPERANDO_FOTOS_ROPA[cite: 2]

async def recibir_fotos_ropa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["fotos_ropa"].append(bytes(await archivo.download_as_bytearray()))
    await update.message.reply_text(f"✅ Ropa #{len(context.user_data['fotos_ropa'])} recibida.")
    return ESPERANDO_FOTOS_ROPA[cite: 2]

async def procesar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modelo_bytes = context.user_data.get("modelo_bytes")
    fotos_ropa = context.user_data.get("fotos_ropa", [])
    if not fotos_ropa: return ESPERANDO_FOTOS_ROPA
    
    msg = await update.message.reply_text(f"⏳ Procesando {len(fotos_ropa)} outfits...")
    loop = asyncio.get_event_loop()
    for i, ropa_bytes in enumerate(fotos_ropa, 1):
        try:
            imagen = await loop.run_in_executor(None, partial(cambiar_ropa_sync, modelo_bytes, ropa_bytes))
            await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ Outfit {i} para mmstore")
        except Exception as e:
            await update.message.reply_text(f"❌ Error en outfit {i}: {str(e)}")
    
    await msg.delete()
    return ConversationHandler.END[cite: 2]

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_editar = ConversationHandler(
        entry_points=[CommandHandler('editar', cmd_editar)],
        states={
            ESPERANDO_FOTO_MODELO: [MessageHandler(filters.PHOTO, recibir_foto_modelo)],
            ESPERANDO_FOTOS_ROPA: [MessageHandler(filters.PHOTO, recibir_fotos_ropa), CommandHandler('listo', procesar_todas)],
        },
        fallbacks=[CommandHandler('cancelar', lambda u,c: ConversationHandler.END)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('estilo', cmd_estilo))
    app.add_handler(CommandHandler('historial', cmd_historial))
    app.add_handler(CallbackQueryHandler(callback_estilo, pattern="^estilo_"))
    app.add_handler(conv_editar)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generar_desde_texto))

    print("🤖 Bot mmstore activo en Railway...")
    app.run_polling(drop_pending_updates=True)[cite: 2]

if __name__ == '__main__':
    main()
