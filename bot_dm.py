# --- CONFIGURACIÓN ---
import os
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI

load_dotenv() # Carga las variables del archivo .env
# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")
AI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODEL_NAME = "gemini-3.8-flash"
ARCHIVO_GUARDADO = "historial.json"

client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Eres un Dungeon Master del sistema de juego Dungeons & Dragons OSE (Old-School Essentials). "
        "REGLAS ESTRICTAS DE PARTIDA:\n"
        "1. NO decidas por los jugadores ni asumas sus acciones. Limítate a describir el entorno, controlar a los NPCs y ofrecer opciones lógicas o preguntar '¿Qué hacéis?'.\n"
        "2. NO tires los dados por los jugadores. Cuando una acción requiera azar (ataque, daño, iniciativa, salvación), pide al jugador que haga la tirada, indícale qué dado usar (ej. 1d20, 1d6) y ESPERA su respuesta en el siguiente mensaje para narrar el resultado.\n"
        "3. Sé descriptivo, oscuro y conciso. Responde siempre en español.\n\n"
        "FICHAS DE PERSONAJES:\n"
        "{\n"
        "  \"Narum El Expulsado\": {\n"
        "    \"Jugador\": \"Alejandro\",\n"
        "    \"Clase\": \"Enano Ladrón Nivel 1\",\n"
        "    \"CA\": 14, \"PG\": 4,\n"
        "    \"Atributos\": {\"FUE\": 13, \"INT\": 11, \"SAB\": 10, \"DES\": 14, \"CON\": 13, \"CAR\": 7},\n"
        "    \"Habilidades\": \"Escalar (87%), Infravisión (60 pies)\",\n"
        "    \"Equipo\": [\"Espada corta (1d6)\", \"Daga (1d4)\", \"Martillo de guerra (1d6)\", \"Honda\", \"Cuerda\", \"Aceite\", \"Yesca\", \"Pimienta\", \"Sal\", \"Poni\"]\n"
        "  },\n"
        "  \"Esquilax El Lagomorfo\": {\n"
        "    \"Jugador\": \"Bastida\",\n"
        "    \"Clase\": \"Mediano Clérigo Nivel 1\",\n"
        "    \"CA\": 16, \"PG\": 6,\n"
        "    \"Atributos\": {\"FUE\": 10, \"INT\": 8, \"SAB\": 15, \"DES\": 13, \"CON\": 15, \"CAR\": 8},\n"
        "    \"Equipo\": [\"Maza (1d6)\", \"Honda\", \"Cota de malla\", \"Escudo\", \"Poni\"]\n"
        "  },\n"
        "  \"Lorek de la Garza\": {\n"
        "    \"Jugador\": \"Fran\",\n"
        "    \"Clase\": \"Humano Guerrero Nivel 1\",\n"
        "    \"CA\": 15, \"PG\": 7,\n"
        "    \"Atributos\": {\"FUE\": 16, \"INT\": 9, \"SAB\": 10, \"DES\": 12, \"CON\": 13, \"CAR\": 11},\n"
        "    \"Combate\": \"Ataque c/c +2\",\n"
        "    \"Equipo\": [\"Espada larga (1d8)\", \"Arco corto\", \"Cota de malla\", \"Escudo\"]\n"
        "  }\n"
        "}"
    )
}

# Funciones de guardado y carga
def cargar_historial():
    if os.path.exists(ARCHIVO_GUARDADO):
        with open(ARCHIVO_GUARDADO, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convertir el ID del grupo de texto a número entero
            return {int(k): v for k, v in data.items()}
    return {}

def guardar_historial(historial):
    with open(ARCHIVO_GUARDADO, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=4)

# Cargar la partida al arrancar
historial_chats = cargar_historial()

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    mensaje_usuario = update.message.text
    bot_username = context.bot.username

    if update.effective_chat.type in ['group', 'supergroup'] and f"@{bot_username}" not in mensaje_usuario:
        return

    mensaje_limpio = mensaje_usuario.replace(f"@{bot_username}", "").strip()
    if not mensaje_limpio:
        return

    nombre_jugador = update.message.from_user.first_name

    if chat_id not in historial_chats:
        historial_chats[chat_id] = [SYSTEM_PROMPT]

    historial_chats[chat_id].append({
        "role": "user",
        "content": f"El jugador {nombre_jugador} dice/hace: {mensaje_limpio}"
    })

    # Aumentado a 50 para que recuerde más historia si vas a meter texto manualmente
    #if len(historial_chats[chat_id]) > 51:
    #    historial_chats[chat_id] = [SYSTEM_PROMPT] + historial_chats[chat_id][-

    # --- SISTEMA DE RESUMEN AUTOMÁTICO ---
    # Cuando llega a 30 mensajes, resume los más antiguos
    if len(historial_chats[chat_id]) > 30:
        try:
            # Extraemos los mensajes viejos a resumir (excluyendo el SYSTEM_PROMPT y los 10 más recientes)
            mensajes_viejos = historial_chats[chat_id][1:-10]
            texto_a_resumir = "\n".join([m["content"] for m in mensajes_viejos if m["role"] != "system"])

            # Pedimos a la IA que cree el resumen
            respuesta_resumen = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Resume los eventos clave, decisiones, ubicaciones y objetos obtenidos de este fragmento de partida de rol. Sé muy conciso, usa viñetas si es necesario y céntrate solo en los hechos."},
                    {"role": "user", "content": texto_a_resumir}
                ],
                max_tokens=400,
                temperature=0.3
            )
            resumen = respuesta_resumen.choices[0].message.content

            # Reconstruimos la memoria: SYSTEM + RESUMEN + 10 ÚLTIMOS MENSAJES
            historial_chats[chat_id] = [
                                           SYSTEM_PROMPT,
                                           {"role": "assistant", "content": f"[MEMORIA DE EVENTOS PASADOS]: {resumen}"}
                                       ] + historial_chats[chat_id][-10:]

        except Exception as e:
            # Si la llamada de resumen falla por red, hace un corte simple para no colapsar
            historial_chats[chat_id] = [SYSTEM_PROMPT] + historial_chats[chat_id][-15:]
    # -------------------------------------

    try:
        respuesta = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=historial_chats[chat_id],
            max_tokens=800,
            temperature=0.8
        )

        texto_dm = respuesta.choices[0].message.content

        historial_chats[chat_id].append({"role": "assistant", "content": texto_dm})

        # Guardar en el archivo tras cada turno
        guardar_historial(historial_chats)

        await update.message.reply_text(texto_dm)

    except Exception as e:
        await update.message.reply_text(f"*(El DM tose sangre)* Error de conexión: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("La partida ha comenzado. Mencionadme con @ para interactuar.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.run_polling()

if __name__ == '__main__':
    main()