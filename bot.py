import logging
import requests
import asyncio
import base64
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from io import BytesIO
from functools import partial

TOKEN = "8778689476:AAGGBgxAf0fWKLiXiO3JN6xWlqAtkDKFKMc"
POLLINATIONS_KEY = "sk_CvmUKUkDU0xnzOTxya9y5JMKgaa16oux"
HISTORIAL_FILE = "historial.json"

ESPERANDO_FOTO_MODELO, ESPERANDO_FOTOS_ROPA = range(2)

logging.basicConfig(level=logging.INFO)

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
    print(f">>> Media upload status: {response.status_code}")
    if response.status_code != 200:
        raise Exception(f"Error subiendo: {response.text}")
    return response.json()["url"]

def mejorar_prompt(prompt, estilo):
    traducciones = {
        "chica": "young woman",
        "chico": "young man",
        "mujer": "woman",
        "hombre": "man",
        "modelo": "fashion model",
        "gym": "modern gym",
        "gimnasio": "modern gym",
        "selfie": "mirror selfie holding iPhone 17 Pro Max",
        "tomandose una selfie": "taking a mirror selfie holding iPhone 17 Pro Max",
        "tomandose": "taking",
        "foto": "photo",
        "ropa": "outfit",
        "deportiva": "athletic wear",
        "cabello": "hair",
        "castaño": "brunette",
        "castaña": "brunette",
        "rubio": "blonde",
        "rubia": "blonde",
        "negro": "black",
        "negra": "black",
        "blanco": "white",
        "blanca": "white",
        "rojo": "red",
        "azul": "blue",
        "verde": "green",
        "playa": "beach",
        "ciudad": "city street",
        "cafe": "coffee shop",
        "restaurante": "restaurant",
        "parque": "park",
        "sonriendo": "smiling",
        "sentada": "sitting",
        "parada": "standing",
        "caminando": "walking",
        "posando": "posing",
        "latina": "latina woman",
        "colombiana": "colombian woman",
        "venezolana": "venezuelan woman",
        "mexicana": "mexican woman",
        "piel": "skin",
        "morena": "tan skin",
        "clara": "fair skin",
        "ojos": "eyes",
        "marrones": "brown",
        "verdes": "green",
        "azules": "blue",
        "largo": "long",
        "corto": "short",
        "rizado": "curly",
        "liso": "straight",
        "sin maquillaje": "no makeup natural look",
        "maquillada": "with makeup",
        "tatuajes": "tattoos",
        "audifonos": "headphones",
        "lentes": "glasses",
        "atardecer": "sunset golden hour",
        "noche": "night",
        "dia": "daytime",
        "interior": "indoors",
        "exterior": "outdoors",
        "espejo": "mirror",
        "fondo": "background",
        "blanco y negro": "black and white"
    }

    prompt_en = prompt.lower()
    for es, en in traducciones.items():
        prompt_en = prompt_en.replace(es, en)

    es_selfie = "selfie" in prompt.lower()

    if es_selfie:
        extra_telefono = (
            "holding iPhone 17 Pro Max taking mirror selfie, "
            "phone clearly visible in hand or mirror reflection, "
        )
    else:
        extra_telefono = (
            "no phone in hand, no device visible, "
            "hands free natural pose, "
        )

    mejoras = {
        "realista": (
            f"full body shot head to toe, wide angle, "
            f"entire body visible in frame, "
            f"{extra_telefono}"
            f"background sharp and in focus no bokeh, "
            f"natural skin texture, subtle pores, "
            f"no heavy freckles, clean skin, "
            f"professional quality photo, "
            f"shot on iPhone 17 Pro Max, 4K resolution, "
            f"natural soft lighting, true to life colors, "
            f"ultra sharp details, high definition, "
            f"unedited authentic photo, real environment"
        ),
        "anime": (
            "anime style, high quality illustration, vibrant colors, "
            "japanese animation, detailed character design, studio quality"
        ),
        "pintura": (
            "oil painting, artistic masterpiece, canvas texture, "
            "fine art, detailed brushstrokes, museum quality"
        ),
        "sketch": (
            "detailed pencil sketch, black and white drawing, "
            "hand drawn, fine lines, artistic illustration"
        )
    }

    prompt_final = f"{prompt_en}, {mejoras.get(estilo, mejoras['realista'])}"
    return prompt_final

def generar_imagen_sync(prompt, estilo="realista"):
    prompt_final = mejorar_prompt(prompt, estilo)
    print(f">>> Prompt original: {prompt}")
    print(f">>> Prompt mejorado: {prompt_final}")

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
    print(f">>> Status: {response.status_code}")
    if response.status_code != 200:
        raise Exception(f"Error: {response.status_code} - {response.text}")
    data = response.json()
    item = data["data"][0]
    if "url" in item:
        return requests.get(item["url"], timeout=60).content
    elif "b64_json" in item:
        return base64.b64decode(item["b64_json"])
    else:
        raise Exception(f"Formato desconocido: {list(item.keys())}")

def cambiar_ropa_sync(imagen_modelo_bytes, imagen_ropa_bytes):
    print(">>> Subiendo imágenes a Pollinations media...")
    url_modelo = subir_a_pollinations(imagen_modelo_bytes)
    url_ropa = subir_a_pollinations(imagen_ropa_bytes)

    prompt = (
        "The person wears the clothing item shown. "
        "Keep all facial features and background the same."
    )

    url = f"https://gen.pollinations.ai/image/{requests.utils.quote(prompt)}"
    params = {
        "model": "qwen-image",
        "image": f"{url_modelo},{url_ropa}",
        "width": "1024",
        "height": "1024",
        "nologo": "true"
    }
    headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"}

    print(f">>> Usando wan-image...")
    response = requests.get(url, headers=headers, params=params, timeout=120)
    print(f">>> Status: {response.status_code}")

    if response.status_code != 200:
        raise Exception(f"Error: {response.status_code} - {response.text[:300]}")

    return response.content

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola! Soy tu bot generador de imágenes\n\n"
        "📌 Comandos:\n"
        "/editar - Cambiar ropa a una modelo\n"
        "/estilo - Cambiar estilo de imagen\n"
        "/historial - Ver tus últimas imágenes\n\n"
        "✏️ Escríbeme en español qué imagen quieres generar!\n\n"
        "Ejemplos:\n"
        "• chica latina selfie gym ropa deportiva verde\n"
        "• mujer rubia playa atardecer vestido rojo\n"
        "• modelo colombiana cafe sonriendo cabello castaño"
    )

async def cmd_estilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📷 Realista", callback_data="estilo_realista"),
            InlineKeyboardButton("🎌 Anime", callback_data="estilo_anime"),
        ],
        [
            InlineKeyboardButton("🎨 Pintura", callback_data="estilo_pintura"),
            InlineKeyboardButton("✏️ Sketch", callback_data="estilo_sketch"),
        ]
    ]
    estilo_actual = context.user_data.get("estilo", "realista")
    await update.message.reply_text(
        f"🎨 Elige el estilo:\n\nEstilo actual: *{estilo_actual}*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def callback_estilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    estilo = query.data.replace("estilo_", "")
    context.user_data["estilo"] = estilo
    nombres = {
        "realista": "📷 Realista",
        "anime": "🎌 Anime",
        "pintura": "🎨 Pintura",
        "sketch": "✏️ Sketch"
    }
    await query.edit_message_text(
        f"✅ Estilo cambiado a: *{nombres[estilo]}*\n\nEscríbeme qué imagen quieres generar!",
        parse_mode="Markdown"
    )

async def generar_desde_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    estilo = context.user_data.get("estilo", "realista")
    msg = await update.message.reply_text(
        f"⏳ Generando imagen en estilo *{estilo}*...",
        parse_mode="Markdown"
    )
    try:
        loop = asyncio.get_event_loop()
        imagen = await loop.run_in_executor(None, partial(generar_imagen_sync, prompt, estilo))
        await update.message.reply_photo(
            photo=BytesIO(imagen),
            caption=f"✅ Listo!\n🎨 Estilo: {estilo}\n📝 {prompt}"
        )
        await msg.delete()
        guardar_en_historial(update.message.from_user.id, prompt, f"generada-{estilo}")
    except Exception as e:
        print(f">>> ERROR: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")

async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["fotos_ropa"] = []
    await update.message.reply_text(
        "👗 Vamos a cambiarle la ropa!\n\n"
        "📸 *Paso 1:* Envíame la foto de la MODELO\n"
        "⚠️ La modelo debe estar de frente",
        parse_mode="Markdown"
    )
    return ESPERANDO_FOTO_MODELO

async def recibir_foto_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    imagen_bytes = await archivo.download_as_bytearray()
    context.user_data["modelo_bytes"] = bytes(imagen_bytes)
    context.user_data["fotos_ropa"] = []
    print(f">>> Foto modelo: {len(imagen_bytes)} bytes")
    await update.message.reply_text(
        "✅ Foto de modelo recibida!\n\n"
        "👕 *Paso 2:* Envíame las fotos de ROPA una por una\n\n"
        "Cuando termines de enviar todas escribe /listo",
        parse_mode="Markdown"
    )
    return ESPERANDO_FOTOS_ROPA

async def recibir_fotos_ropa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1]
    archivo = await foto.get_file()
    ropa_bytes = await archivo.download_as_bytearray()

    context.user_data["fotos_ropa"].append(bytes(ropa_bytes))
    total = len(context.user_data["fotos_ropa"])

    print(f">>> Foto ropa #{total} recibida")
    await update.message.reply_text(
        f"✅ Ropa #{total} recibida!\n\n"
        f"Envía más fotos de ropa o escribe /listo para procesar"
    )
    return ESPERANDO_FOTOS_ROPA

async def procesar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    modelo_bytes = context.user_data.get("modelo_bytes")
    fotos_ropa = context.user_data.get("fotos_ropa", [])

    if not fotos_ropa:
        await update.message.reply_text("❌ No enviaste ninguna foto de ropa!")
        return ESPERANDO_FOTOS_ROPA

    total = len(fotos_ropa)
    msg = await update.message.reply_text(
        f"⏳ Procesando {total} cambio(s) de ropa, espera..."
    )

    loop = asyncio.get_event_loop()
    errores = 0

    for i, ropa_bytes in enumerate(fotos_ropa, 1):
        try:
            await msg.edit_text(f"⏳ Procesando outfit {i} de {total}...")
            imagen_editada = await loop.run_in_executor(
                None, partial(cambiar_ropa_sync, modelo_bytes, ropa_bytes)
            )
            await update.message.reply_photo(
                photo=BytesIO(imagen_editada),
                caption=f"✅ Outfit {i} de {total} 👗"
            )
            guardar_en_historial(update.message.from_user.id, f"cambio ropa {i}", "editada")
        except Exception as e:
            errores += 1
            print(f">>> ERROR outfit {i}: {e}")
            await update.message.reply_text(f"❌ Error en outfit {i}: {str(e)}")

    await msg.edit_text(
        f"✅ Listo! Procesados {total - errores} de {total} outfits 👗"
    )

    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.")
    return ConversationHandler.END

async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    historial = cargar_historial()
    user_id = str(update.message.from_user.id)
    if user_id not in historial or not historial[user_id]:
        await update.message.reply_text("📭 No tienes imágenes generadas aún.")
        return
    items = historial[user_id][-10:]
    texto = "📚 *Tus últimas imágenes:*\n\n"
    for i, item in enumerate(reversed(items), 1):
        texto += f"{i}. [{item['tipo']}] {item['prompt']}\n   📅 {item['fecha']}\n\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()

    conv_editar = ConversationHandler(
        entry_points=[CommandHandler('editar', cmd_editar)],
        states={
            ESPERANDO_FOTO_MODELO: [
                MessageHandler(filters.PHOTO, recibir_foto_modelo)
            ],
            ESPERANDO_FOTOS_ROPA: [
                MessageHandler(filters.PHOTO, recibir_fotos_ropa),
                CommandHandler('listo', procesar_todas)
            ],
        },
        fallbacks=[CommandHandler('cancelar', cancelar)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('estilo', cmd_estilo))
    app.add_handler(CommandHandler('historial', cmd_historial))
    app.add_handler(CallbackQueryHandler(callback_estilo, pattern="^estilo_"))
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
