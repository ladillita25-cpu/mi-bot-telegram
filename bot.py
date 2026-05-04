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
# Usamos .strip() para evitar cualquier espacio invisible que cause el error "Invalid Key"
POLLINATIONS_KEY = "sk_CvmUKUkDU0xnzOTxya9y5JMKgaa16oux".strip()
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

# --- FUNCIÓN CRÍTICA DE SUBIDA (MODIFICADA) ---
def subir_a_pollinations(imagen_bytes):
    # Algunos servidores de Pollinations requieren Content-Type explícito y Headers limpios
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_KEY}",
        "Accept": "application/json"
    }
    
    files = {
        "file": ("image.jpg", imagen_bytes, "image/jpeg")
    }
    
    try:
        response = requests.post(
            "https://media.pollinations.ai/upload",
            headers=headers,
            files=files,
            timeout=40
        )
        
        print(f">>> Media upload status: {response.status_code}")
        
        if response.status_code != 200:
            # Si da 401 o 403, el error es definitivamente la Key o falta de créditos
            error_msg = response.json().get("error", response.text)
            raise Exception(f"Status {response.status_code}: {error_msg}")
            
        return response.json()["url"]
    except Exception as e:
        raise Exception(f"Fallo en la comunicación con el servidor de subida: {str(e)}")

def mejorar_prompt(prompt, estilo):
    traducciones = {
        "chica": "young woman", "chico": "young man", "mujer": "woman",
        "hombre": "man", "modelo": "fashion model", "gym": "modern gym",
        "gimnasio": "modern gym", "selfie": "mirror selfie holding iPhone 17 Pro Max",
        "ropa": "outfit", "deportiva": "athletic wear", "cabello": "hair",
        "castaño": "brunette", "rubio": "blonde", "negro": "black",
        "latina": "latina woman", "tatuajes": "tattoos", "audifonos": "headphones"
    }

    prompt_en = prompt.lower()
    for es, en in traducciones.items():
        prompt_en = prompt_en.replace(es, en)

    es_selfie = "selfie" in prompt.lower()
    extra_telefono = "holding iPhone 17 Pro Max taking mirror selfie, " if es_selfie else "hands free natural pose, "

    mejoras = {
        "realista": (
            f"full body shot, {extra_telefono} natural skin texture, "
            f"shot on iPhone 17 Pro Max, 4K, ultra sharp, unedited authentic photo"
        ),
        "anime": "anime style, high quality illustration, studio quality",
        "pintura": "oil painting, artistic masterpiece, detailed brushstrokes",
        "sketch": "detailed pencil sketch, hand drawn, fine lines"
    }

    return f"{prompt_en}, {mejoras.get(estilo, mejoras['realista'])}"

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
        raise Exception(f"Error {response.status_code}: {response.text}")
    
    data = response.json()
    item = data["data"][0]
    return requests.get(item["url"], timeout=60).content

# --- FUNCIÓN DE CAMBIO DE ROPA (WAN-IMAGE) ---
def cambiar_ropa_sync(imagen_modelo_bytes, imagen_ropa_bytes):
    print(">>> Iniciando proceso de cambio de ropa...")
    url_modelo = subir_a_pollinations(imagen_modelo_bytes)
    url_ropa = subir_a_pollinations(imagen_ropa_bytes)

    seed = random.randint(1, 999999)
    prompt = (
        "Clothing swap task. Take the EXACT garment from Image 2 and put it on the person in Image 1. "
        "Keep face, hair and background exactly as Image 1. Photorealistic."
    )

    url = f"https://gen.pollinations.ai/image/{requests.utils.quote(prompt)}"
    params = {
        "model": "wan-image",
        "image": f"{url_modelo},{url_ropa}",
        "width": "1024",
        "height": "1024",
        "nologo": "true",
        "seed": str(seed)
    }
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}

    response = requests.get(url, headers=headers, params=params, timeout=150)
    if response.status_code != 200:
        raise Exception(f"Error en generación: {response.status_code} - {response.text[:200]}")

    return response.content

# --- HANDLERS DE TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Soy tu bot de mmstore. Usa /editar para cambiar ropa.")

async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📸 *Paso 1:* Envíame la foto de la MODELO", parse_mode="Markdown")
    return ESPERANDO_FOTO_MODELO

async def recibir_foto_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["modelo_bytes"] = bytes(await archivo.download_as_bytearray())
    context.user_data["fotos_ropa"] = []
    await update.message.reply_text("👕 *Paso 2:* Envíame las fotos de ROPA. Escribe /listo al terminar.", parse_mode="Markdown")
    return ESPERANDO_FOTOS_ROPA

async def recibir_fotos_ropa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    context.user_data["fotos_ropa"].append(bytes(await archivo.download_as_bytearray()))
    await update.message.reply_text(f"✅ Ropa #{len(context.user_data['fotos_ropa'])} recibida. ¿Otra o /listo?")
    return ESPERANDO_FOTOS_ROPA

async def procesar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modelo_bytes = context.user_data.get("modelo_bytes")
    fotos_ropa = context.user_data.get("fotos_ropa", [])
    
    if not fotos_ropa:
        await update.message.reply_text("❌ No hay ropa para procesar.")
        return ConversationHandler.END

    msg = await update.message.reply_text("⏳ Procesando, esto puede tardar un poco...")
    loop = asyncio.get_event_loop()

    for i, ropa_bytes in enumerate(fotos_ropa, 1):
        try:
            imagen = await loop.run_in_executor(None, partial(cambiar_ropa_sync, modelo_bytes, ropa_bytes))
            await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ Outfit {i} listo")
        except Exception as e:
            await update.message.reply_text(f"❌ Error en outfit {i}: {str(e)}")

    await msg.edit_text("✅ Proceso finalizado.")
    return ConversationHandler.END

async def generar_desde_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    estilo = context.user_data.get("estilo", "realista")
    msg = await update.message.reply_text(f"⏳ Generando...")
    try:
        loop = asyncio.get_event_loop()
        imagen = await loop.run_in_executor(None, partial(generar_imagen_sync, prompt, estilo))
        await update.message.reply_photo(photo=BytesIO(imagen), caption=f"✅ {prompt}")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

# --- MAIN ---
def main():
    app = Application.builder().token(TOKEN).build()

    conv_editar = ConversationHandler(
        entry_points=[CommandHandler('editar', cmd_editar)],
        states={
            ESPERANDO_FOTO_MODELO: [MessageHandler(filters.PHOTO, recibir_foto_modelo)],
            ESPERANDO_FOTOS_ROPA: [
                MessageHandler(filters.PHOTO, recibir_fotos_ropa),
                CommandHandler('listo', procesar_todas)
            ],
        },
        fallbacks=[CommandHandler('cancelar', cancelar)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_editar)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generar_desde_texto))

    print("🤖 Bot corriendo...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

    print("🤖 Bot corriendo...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
