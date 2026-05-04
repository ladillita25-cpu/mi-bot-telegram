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
TOKEN = "8778689476:AAGGBgxAf0fWKLiXiO3JN6xWlqAtkDKFKMc"
POLLINATIONS_KEY = "sk_D2WPFQYpfT1Rl5mJvFJ7bJhKZQMBVYBc"
HISTORIAL_FILE = "historial.json"

ESPERANDO_FOTO_MODELO, ESPERANDO_FOTOS_ROPA = range(2)

logging.basicConfig(level=logging.INFO)

# --- FUNCIONES DE UTILIDAD ---
def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

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
    historial[user_id] = historial[user_id][-20:]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)

def subir_a_pollinations(imagen_bytes):
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}
    response = requests.post(
        "https://media.pollinations.ai/upload",
        headers=headers,
        files={"file": ("image.jpg", imagen_bytes, "image/jpeg")},
        timeout=30
    )
    if response.status_code != 200:
        raise Exception(f"Error al subir imagen: {response.text}")
    return response.json()["url"]

def mejorar_prompt(prompt, estilo):
    traducciones = {
        "chica": "young woman", "chico": "young man", "mujer": "woman",
        "hombre": "man", "modelo": "fashion model", "gym": "modern gym",
        "gimnasio": "modern gym", "selfie": "mirror selfie holding iPhone 17 Pro Max",
        "latina": "latina woman", "colombiana": "colombian woman", "morena": "tan skin"
    }

    prompt_en = prompt.lower()
    for es, en in traducciones.items():
        prompt_en = prompt_en.replace(es, en)

    es_selfie = "selfie" in prompt.lower()
    extra_telefono = "holding iPhone 17 Pro Max taking mirror selfie, phone clearly visible, " if es_selfie else "no phone in hand, hands free natural pose, "

    mejoras = {
        "realista": f"full body shot, entire body visible, {extra_telefono} natural skin texture, professional quality, shot on iPhone 17 Pro Max, 4K resolution, authentic photo",
        "anime": "anime style, high quality illustration, vibrant colors, studio quality",
        "pintura": "oil painting, artistic masterpiece, detailed brushstrokes",
        "sketch": "detailed pencil sketch, black and white drawing, hand drawn"
    }

    return f"{prompt_en}, {mejoras.get(estilo, mejoras['realista'])}"

# --- FUNCIONES DE GENERACIÓN ---
def generar_imagen_sync(prompt, estilo="realista"):
    prompt_final = mejorar_prompt(prompt, estilo)
    url = "https://gen.pollinations.ai/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "prompt": prompt_final,
        "model": "flux",
        "width": 832,
        "height": 1216,
        "n": 1,
        "enhance": True
    }

    response = requests.post(url, headers=headers, json=body, timeout=120)
    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}")
    
    data = response.json()
    item = data["data"][0]
    return requests.get(item["url"], timeout=60).content

# --- FUNCIÓN MODIFICADA PARA EDICIÓN ---
def cambiar_ropa_sync(imagen_modelo_bytes, imagen_ropa_bytes):
    print(">>> Iniciando proceso de edición con Wan...")
    url_modelo = subir_a_pollinations(imagen_modelo_bytes)
    url_ropa = subir_a_pollinations(imagen_ropa_bytes)

    seed = random.randint(1, 999999)

    # Prompt simplificado para evitar errores de interpretación en el worker
    prompt_edicion = (
        f"Clothing swap task: Replace the clothes of the person in the base image with the exact outfit from the reference garment image. "
        "Maintain the face, pose and background of the base image perfectly."
    )

    # URL base de Pollinations para procesamiento de imagen
    url = f"https://gen.pollinations.ai/image/{requests.utils.quote(prompt_edicion)}"
    
    # Parámetros optimizados para Wan-Image
    params = {
        "model": "wan-image",
        "image": url_modelo,     # Imagen base (la modelo)
        "ref_image": url_ropa,   # Imagen de referencia (la ropa)
        "width": 1024,
        "height": 1024,
        "seed": str(seed),
        "nologo": "true"
    }
    
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}

    # Aumentamos el timeout a 300 segundos para Railway
    print(f">>> Enviando petición a Wan-Image (Seed: {seed})...")
    response = requests.get(url, headers=headers, params=params, timeout=300)
    
    if response.status_code != 200:
        print(f">>> ERROR API: {response.text}")
        raise Exception(f"Servidor ocupado (Error {response.status_code}). Intenta de nuevo en unos segundos.")

    return response.content

# --- HANDLERS DE TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot generador de moda.\n\n"
        "📌 Comandos:\n"
        "/editar - Cambiar ropa a una modelo\n"
        "/estilo - Elegir estilo visual\n"
        "/historial - Ver tus creaciones\n\n"
        "Escríbeme un prompt para empezar."
    )

async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👗 *Modo Edición*\n\n"
        "1. Envíame la foto de la MODELO.",
        parse_mode="Markdown"
    )
    return ESPERANDO_FOTO_MODELO

async def recibir_foto_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["modelo_bytes"] = bytes(await archivo.download_as_bytearray())
    context.user_data["fotos_ropa"] = []
    await update.message.reply_text("✅ Modelo recibida. Ahora envíame la foto de la PRENDA/ROPA.")
    return ESPERANDO_FOTOS_ROPA

async def recibir_fotos_ropa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    ropa_bytes = await archivo.download_as_bytearray()
    context.user_data["fotos_ropa"].append(bytes(ropa_bytes))
    await update.message.reply_text("✅ Ropa añadida. Envía otra o escribe /listo.")
    return ESPERANDO_FOTOS_ROPA

async def procesar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modelo_bytes = context.user_data.get("modelo_bytes")
    fotos_ropa = context.user_data.get("fotos_ropa", [])

    if not fotos_ropa:
        await update.message.reply_text("❌ No hay fotos de ropa.")
        return ESPERANDO_FOTOS_ROPA

    msg = await update.message.reply_text(f"⏳ Procesando {len(fotos_ropa)} outfit(s)... esto puede tardar un minuto.")
    loop = asyncio.get_event_loop()

    for i, ropa_bytes in enumerate(fotos_ropa, 1):
        try:
            imagen = await loop.run_in_executor(None, partial(cambiar_ropa_sync, modelo_bytes, ropa_bytes))
            await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ Outfit {i} completado.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error en outfit {i}: {str(e)}")

    await msg.delete()
    return ConversationHandler.END

# --- RESTO DE COMANDOS Y MAIN ---
async def generar_desde_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    msg = await update.message.reply_text("⏳ Generando...")
    try:
        loop = asyncio.get_event_loop()
        imagen = await loop.run_in_executor(None, partial(generar_imagen_sync, prompt, context.user_data.get("estilo", "realista")))
        await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ {prompt}")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_editar = ConversationHandler(
        entry_points=[CommandHandler('editar', cmd_editar)],
        states={
            ESPERANDO_FOTO_MODELO: [MessageHandler(filters.PHOTO, recibir_foto_modelo)],
            ESPERANDO_FOTOS_ROPA: [MessageHandler(filters.PHOTO, recibir_fotos_ropa), CommandHandler('listo', procesar_todas)],
        },
        fallbacks=[CommandHandler('cancelar', lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(conv_editar)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generar_desde_texto))
    
    print("🤖 Bot iniciado en Railway...")
    app.run_polling()

if __name__ == '__main__':
    main()
```[cite: 1, 2]
