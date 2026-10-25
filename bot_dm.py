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
AI_BASE_URL = "http://127.0.0.1:8080/v1"
MODEL_NAME = os.getenv("MODELNAME")
ARCHIVO_GUARDADO = "historial.json"

client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Eres el Dungeon Master (DM) de una partida de D&D OSE. TÚ NO ERES UN PERSONAJE, eres el narrador invisible y omnisciente. NUNCA hables en primera persona ('yo me desperté', 'me acerqué a la mesa'). Dirígete a los jugadores en segunda persona ('vosotros estáis', 'Narum, tú ves...').\n\n"
        "REGLAS SUPREMAS (¡CUMPLE ESTO ESTRICTAMENTE!):\n"
        "1. PROHIBIDO CONTROLAR A LOS JUGADORES: NUNCA escribas los diálogos, acciones o pensamientos de Narum, Esquilax o Lorek. Esos personajes los controlan humanos reales. Si hacen una pregunta, responde tú como narrador o usa a un NPC, pero NUNCA hagas que Narum o Lorek hablen solos.\n"
        "2. ANTI-ALUCINACIÓN: TIENES PROHIBIDO inventar lugares, cuevas o tramas genéricas. SOLO puedes basarte en la sección [ESCENARIO ACTUAL].\n"
        "3. REGLA DEL ASTERISCO (*): Si el mensaje del usuario empieza con un asterisco, es el HUMANO hablando contigo. NO respondas como NPC. Acata la corrección aplicando la regla como un Director de Juego, sin pedir disculpas como un asistente IA ni romper la inmersión.\n"
        "4. Responde siempre en español. Describe la escena, controla ÚNICAMENTE a los NPCs (Garin, Bran, Vane) y TERMINA tu turno siempre preguntando '¿Qué hacéis?'.\n\n"
        "5. TIRADAS OBLIGATORIAS: NUNCA resuelvas automáticamente una acción si hay posibilidad de fallo (robar, atacar, mentir). Detén la narración, pide la tirada de dados indicando la dificultad (CD) y espera la respuesta del jugador.\n"
        "6. ECONOMÍA REALISTA: Aplica los precios de D&D. Comida, bebida o alojamiento cuestan piezas de cobre (pc) o plata (pp). Nunca cobres en oro (po) por cosas mundanas.\n"
        "[ESCENARIO ACTUAL - TU ÚNICA VERDAD]\n"
        "- Lugar: Las calles embarradas y tabernas de la ciudad fronteriza de Lindenburgo.\n"
        "- Personajes Jugadores (Intocables para ti): Narum (Enano Ladrón), Esquilax (Mediano Clérigo) y Lorek (Humano Guerrero).\n"
        "- NPCs Aliados presentes (Bajo tu control): Garin y Bran (Mercenarios). Monturas: Ponyo, Boris y Roble.\n"
        "- Contexto: El grupo acaba de aniquilar a la tribu goblin 'Colmillo Roto', recuperando sal para 'El Tuerto Vane' (Sindicato de la Sal). Ya han cobrado su recompensa.\n"
        "- Situación: Tienen 574 monedas de oro (po) entre todos. Están en la ciudad debatiendo qué hacer con el oro: explorar los túmulos antiguos o buscar otra inversión.\n\n"
        "[FICHAS DE PERSONAJES E INVENTARIOS]\n"
        "- Narum El Expulsado (Enano Ladrón 1): CA 14, PG 4. FUE 13, INT 11, SAB 10, DES 14, CON 13, CAR 7. Escalar 87%, Infravisión 60'. Ataque: C/C +1, Dis +1. Oro: 178 po, 44 pp, 12 pc. Equipo: Daga (1d4), espada corta (1d6), martillo de guerra (1d6), odre vinagre, 2 odres agua, mochila (garfio, cuerda, puntas hierro, honda y 20 proyectiles, yesca, antorcha, vendas, sartén, velas, cataplasmas, pimienta, 2 aceites, raciones), poni (Ponyo), alforjas, botella vino, anillo jade (25 po), daga marinero, mapa náutico.\n"
        "- Esquilax El Lagomorfo (Mediano Clérigo 1): CA 16, PG 6. FUE 10, INT 8, SAB 15, DES 13, CON 15, CAR 8. Ataque: C/C +0, Dis +1. Oro: 195 po, 10 pp, 12 pc. Equipo: Maza (1d6), honda (20 proyectiles), cota de malla, escudo, raciones, poni (Boris), alforjas, Sal Bendita.\n"
        "- Lorek de la Garza (Humano Guerrero 1): CA 15, PG 7. FUE 16, INT 9, SAB 10, DES 12, CON 13, CAR 11. Ataque C/C +2. Oro: 176 po, 7 pp, 25 pc. Equipo: Espada larga (1d8), arco corto y carcaj (20 flechas), cota de malla, escudo, odre agua, raciones, 5 antorchas, yesca, caballo (Roble), alforjas.\n\n"
        "[INSTRUCCIÓN DE ARRANQUE OBLIGATORIA]\n"
        "Si te preguntan dónde están, descríbelo en segunda persona ('Vosotros estáis...'). Recuerda que NO PUEDES decidir qué dicen o hacen Narum, Esquilax o Lorek."
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
    mensaje = update.effective_message
    if not mensaje or not mensaje.text:
        return

    mensaje_usuario = mensaje.text
    bot_username = context.bot.username
    nombre_jugador = mensaje.from_user.first_name

    # 1. Verificar si es un grupo y si el bot es mencionado
    if update.effective_chat.type in ['group', 'supergroup'] and f"@{bot_username}" not in mensaje_usuario:
        return

    # 2. Limpiar la mención para aislar el texto real
    mensaje_limpio = mensaje_usuario.replace(f"@{bot_username}", "").strip()
    if not mensaje_limpio:
        return

    # 3. Interceptar el asterisco para hablar de DM a Jugador de forma natural
    if mensaje_limpio.startswith("*"):
        mensaje_final = (
            f"(OOC - Fuera de rol. El jugador pregunta: '{mensaje_limpio}'. "
            "Responde a esto como el Dungeon Master humano hablando de tú a tú con el jugador en la mesa. "
            "Aclárale la duda de forma natural basándote en el [ESCENARIO ACTUAL], pero NO hables como un robot ni digas 'error del sistema'.)"
        )
    else:
        mensaje_final = f"El jugador {nombre_jugador} dice/hace: {mensaje_limpio}"

    if chat_id not in historial_chats:
        historial_chats[chat_id] = [SYSTEM_PROMPT]

    # SE GUARDA mensaje_final PARA QUE SE APLIQUE LA REGLA DEL ASTERISCO
    historial_chats[chat_id].append({
        "role": "user",
        "content": mensaje_final
    })

    # --- SISTEMA DE RESUMEN AUTOMÁTICO ---
    if len(historial_chats[chat_id]) > 30:
        try:
            mensajes_viejos = historial_chats[chat_id][1:-10]
            texto_a_resumir = "\n".join([m["content"] for m in mensajes_viejos if m["role"] != "system"])

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

            historial_chats[chat_id] = [
                                           SYSTEM_PROMPT,
                                           {"role": "assistant", "content": f"[MEMORIA DE EVENTOS PASADOS]: {resumen}"}
                                       ] + historial_chats[chat_id][-10:]

        except Exception as e:
            historial_chats[chat_id] = [SYSTEM_PROMPT] + historial_chats[chat_id][-15:]
    # -------------------------------------

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        respuesta = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=historial_chats[chat_id],
            max_tokens=800,
            temperature=0.3
        )

        texto_dm = respuesta.choices[0].message.content

        historial_chats[chat_id].append({"role": "assistant", "content": texto_dm})

        guardar_historial(historial_chats)

        await update.message.reply_text(texto_dm)

    except Exception as e:
        # Extraer el mensaje del usuario si hay fallo para no corromper la memoria
        historial_chats[chat_id].pop()
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