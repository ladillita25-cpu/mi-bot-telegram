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
# Token de Telegram
TOKEN = "8778689476:AAGGBgxAf0fWKLiXiO3JN6xWlqAtkDKFKMc"[cite: 2]

# Intentar leer la clave de Railway. Si no existe, usa la que pusimos aquí.
# RECOMENDACIÓN: Actualiza la clave en la pestaña 'Variables' de Railway como "POLLINATIONS_KEY"
POLLINATIONS_KEY = os.getenv("POLLINATIONS_KEY", "sk_D2WPFQYpfT1Rl5mJvFJ7bJhKZQMBVYBc")[cite: 2]

HISTORIAL_FILE = "historial.json"[cite: 2]

ESPERANDO_FOTO_MODELO, ESPERANDO_FOTOS_ROPA = range(2)[cite: 2]

logging.basicConfig(level=logging.INFO)

# --- SISTEMA DE HISTORIAL ---
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
        # Esto nos dirá exactamente qué dice el servidor si la clave falla
        raise Exception(f"Error de API: {response.text}") 
    return response.json()["url"][cite: 2]

# --- TRADUCCIÓN Y PROMPTS ---
def mejorar_prompt(prompt, estilo):
    traducciones = {
        "chica": "young woman", "chico": "young man", "mujer": "woman",
        "hombre": "man", "modelo": "fashion model", "gym": "modern gym",
        "selfie": "mirror selfie holding iPhone 17 Pro Max",
        "latina": "latina woman", "morena": "tan skin", "ropa": "outfit"
    }[cite: 2]

    prompt_en = prompt.lower()
    for es, en in traducciones.items():
        prompt_en = prompt_en.replace(es, en)

    es_selfie = "selfie" in prompt.lower()
    extra_telefono = "holding iPhone 17 Pro Max taking mirror selfie, " if es_selfie else "no phone in hand, "

    mejoras = {
        "realista": f"full body shot, {extra_telefono} natural skin, professional photo, 4K",
        "anime": "anime style, high quality illustration",
        "pintura": "oil painting, artistic masterpiece",
        "sketch": "detailed pencil sketch, black and white"
    }[cite: 2]

    return f"{prompt_en}, {mejoras.get(estilo, mejoras['realista'])}"

# --- GENERACIÓN Y EDICIÓN ---
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
        raise Exception(f"Error Generación: {response.status_code}")
    
    data = response.json()
    item = data["data"][0]
    return requests.get(item["url"], timeout=60).content[cite: 2]

def cambiar_ropa_sync(imagen_modelo_bytes, imagen_ropa_bytes):
    url_modelo = subir_a_pollinations(imagen_modelo_bytes)
    url_ropa = subir_a_pollinations(imagen_ropa_bytes)
    seed = random.randint(1, 999999)

    prompt = "Clothing swap: put the clothes from the reference image on the person. High quality."[cite: 2]
    url = f"https://gen.pollinations.ai/image/{requests.utils.quote(prompt)}"
    
    params = {
        "model": "wan-image",
        "image": url_modelo,
        "ref_image": url_ropa,
        "width": 1024, "height": 1024,
        "nologo": "true", "seed": str(seed)
    }[cite: 2]
    
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}
    response = requests.get(url, headers=headers, params=params, timeout=300)
    
    if response.status_code != 200:
        raise Exception(f"Error Wan-Image: {response.text}")
    return response.content[cite: 2]

# --- HANDLERS DE TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Bot listo! Usa /editar para probar outfits.")[cite: 2]

async def cmd_estilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📷 Realista", callback_data="estilo_realista")]]
    await update.message.reply_text("Elige estilo:", reply_markup=InlineKeyboardMarkup(keyboard))[cite: 2]

async def callback_estilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["estilo"] = query.data.replace("estilo_", "")
    await query.edit_message_text(f"Estilo: {context.user_data['estilo']}")[cite: 2]

async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👗 Envía la foto de la MODELO.")
    return ESPERANDO_FOTO_MODELO[cite: 2]

async def recibir_foto_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["modelo_bytes"] = bytes(await archivo.download_as_bytearray())
    context.user_data["fotos_ropa"] = []
    await update.message.reply_text("✅ Ahora envía la foto de la ROPA y escribe /listo.")
    return ESPERANDO_FOTOS_ROPA[cite: 2]

async def recibir_fotos_ropa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["fotos_ropa"].append(bytes(await archivo.download_as_bytearray()))
    await update.message.reply_text(f"✅ Ropa #{len(context.user_data['fotos_ropa'])} añadida.")
    return ESPERANDO_FOTOS_ROPA[cite: 2]

async def procesar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modelo_bytes = context.user_data.get("modelo_bytes")
    fotos_ropa = context.user_data.get("fotos_ropa", [])
    if not fotos_ropa: return ESPERANDO_FOTOS_ROPA
    
    msg = await update.message.reply_text("⏳ Procesando... esto tardará un poco.")
    loop = asyncio.get_event_loop()
    for i, ropa_bytes in enumerate(fotos_ropa, 1):
        try:
            imagen = await loop.run_in_executor(None, partial(cambiar_ropa_sync, modelo_bytes, ropa_bytes))
            await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ Resultado {i}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    await msg.delete()
    return ConversationHandler.END

async def generar_desde_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    msg = await update.message.reply_text("⏳ Generando...")
    try:
        loop = asyncio.get_event_loop()
        imagen = await loop.run_in_executor(None, partial(generar_imagen_sync, prompt, context.user_data.get("estilo", "realista")))
        await update.message.reply_photo(photo=BytesIO(imagen))
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")[cite: 2]

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
    app.add_handler(CallbackQueryHandler(callback_estilo, pattern="^estilo_"))
    app.add_handler(conv_editar)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generar_desde_texto))

    print("🤖 Bot iniciado...")
    app.run_polling(drop_pending_updates=True)[cite: 2]

if __name__ == '__main__':
    main()
