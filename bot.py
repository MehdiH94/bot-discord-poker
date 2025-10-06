import matplotlib.pyplot as plt
import discord
from discord.ext import commands
import asyncio
import json
import os
from dotenv import load_dotenv
from datetime import datetime
import aiofiles
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("CHANGE_PREFIX", "/")  # tu peux changer le préfixe via .env

DATA_FILE = "sessions.json"
ATTACH_DIR = "attachments"
os.makedirs(ATTACH_DIR, exist_ok=True)

# Intents : on a besoin d'accéder au contenu des messages
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
file_lock = asyncio.Lock()          # évite collisions lors de l'écriture sur sessions.json
active_sessions = {}                # user_id -> True (pour empêcher double session)

QUESTIONS = [
    ("Date de la session ? (YYYY-MM-DD)", "date"),
    ("Lieu de la session ?", "lieu"),
    ("Résultat net (DTS) ? (ex: +120 ou -50)", "resultat"),
    ("Buy-in ?", "buyin"),
    ("Nombre d'heure ?", "heures"),
    ("Combien as-tu respecté ton plan ? sur 10", "plan_respecte"),
    ("Niveau de tilt sur 10 ?", "tilt"),
    ("Les mains clés (décris la main, tu peux aussi joindre url)", "main_cle"),
    ("Nombre d'erreur grossieres ?", "erreur"),
    ("Nombre de call muck ?", "call_muck"),
    ("As-tu pris ton temps oui/non?", "patience"),
    ("Un point positif ?", "points_positifs"),
    ("Action corrective pour la prochaine fois ?", "action_corrective"),
]

# helper: charge le fichier JSON (ou initialise)
async def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    async with aiofiles.open(DATA_FILE, "r", encoding="utf-8") as f:
        text = await f.read()
        return json.loads(text) if text.strip() else []

# helper: écriture atomique
async def save_data(data):
    tmp = DATA_FILE + ".tmp"
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, DATA_FILE)

@bot.event
async def on_ready():
    print(f"Connecté comme {bot.user} (id: {bot.user.id})")
    print("Bot prêt. Lance /session dans ton serveur.")

@bot.command(name="session")
async def start_session(ctx):
    author = ctx.author
    if author.bot:
        return

    if author.id in active_sessions:
        await ctx.send(f"{author.mention} Tu as déjà une session en cours. Termine-la ou attends qu'elle expire.")
        return

    active_sessions[author.id] = True
    await ctx.send(f"{author.mention} Démarrage du questionnaire. Tape `stop` pour annuler. (Timeout 3 minutes par question).")

    session = {
        "user_id": author.id,
        "user_name": str(author),
        "created_at_utc": datetime.utcnow().isoformat() + "Z"
    }

    def check(m):
        return m.author == author and m.channel == ctx.channel

    try:
        for prompt, key in QUESTIONS:
            await ctx.send(prompt)
            try:
                msg = await bot.wait_for("message", check=check, timeout=180)  # 3 minutes
            except asyncio.TimeoutError:
                await ctx.send(f"{author.mention} Temps écoulé — session annulée (réponds plus vite la prochaine fois).")
                return

            if msg.content.lower() in ("stop", "cancel", "annuler"):
                await ctx.send("Session annulée comme demandé.")
                return

            # si attachment présent, on le télécharge et on stocke le chemin
            if msg.attachments:
                att = msg.attachments[0]
                filename = f"{author.id}_{int(datetime.utcnow().timestamp())}_{att.filename}"
                path = os.path.join(ATTACH_DIR, filename)
                await att.save(path)
                session[key] = {"text": msg.content.strip(), "attachment_path": path}
            else:
                session[key] = msg.content.strip()

    finally:
        # on retire de active_sessions dans tous les cas
        active_sessions.pop(author.id, None)

    # écriture dans le fichier JSON (protégée)
    async with file_lock:
        data = await load_data()
        data.append(session)
        await save_data(data)

    await ctx.send("✅ Session enregistrée dans `sessions.json` !")

@bot.command(name="derniere_session")
async def derniere_session(ctx):
    user_id = ctx.author.id
    async with file_lock:
        data = await load_data()
    user_sessions = [s for s in data if s.get("user_id") == user_id]
    if not user_sessions:
        await ctx.send("Tu n'as aucune session enregistrée.")
        return
    last = user_sessions[-1]
    summary = (
        f"**Session**: {last.get('date','n/a')} — {last.get('lieu','n/a')}\n"
        f"Résultat: {last.get('resultat','n/a')} DTS\n"
        f"Buy-in: {last.get('buyin','n/a')} DTS\n"
        f"Tilt: {last.get('tilt','n/a')}\n"
        f"Nombre d'heures: {last.get('heures','n/a')}\n"
        f"Action corrective: {last.get('action_corrective','n/a')}"
        f"Plan respecté: {last.get('plan_respecte','n/a')}"
        f"Nombre d'erreurs grossieres: {last.get('erreur','n/a')}"
        f"Nombre de call muck: {last.get('call_muck','n/a')}"
        f"As-tu pris ton temps: {last.get('patience','n/a')}"
    )
    await ctx.send(summary)
    # si main_cle a une pièce jointe, propose l'envoyer
    mc = last.get("main_cle")
    if isinstance(mc, dict) and mc.get("attachment_path") and os.path.exists(mc["attachment_path"]):
        await ctx.send("Voici la pièce jointe pour la main clé :", file=discord.File(mc["attachment_path"]))

@bot.command(name="export_sessions")
async def export_sessions(ctx):
    # envoie le fichier sessions.json en pièce jointe (si existe)
    async with file_lock:
        if not os.path.exists(DATA_FILE):
            await ctx.send("Aucune donnée à exporter.")
            return
    await ctx.send(file=discord.File(DATA_FILE))

# commande pour vérifier que le bot est vivant
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("pong")

@bot.command(name="stats")
async def stats(ctx):
    async with file_lock:
        data = await load_data()

    if not data:
        await ctx.send("⚠️ Aucune session enregistrée pour l’instant.")
        return

    from collections import defaultdict
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np

    def parse_float(val):
        try:
            return float(str(val).replace("DTS", "").replace(" ", ""))
        except:
            return 0.0

    def safe_int(val):
        try:
            if val is None or str(val).strip().lower() in ("", "n/a"):
                return None
            return int(val)
        except ValueError:
            return None

    # Grouper par joueur
    players = defaultdict(list)
    for s in data:
        players[s.get("user_id")].append(s)

    for user_id, sessions in players.items():
        user_name = sessions[0].get("user_name", f"User {user_id}")
        sessions = sorted(sessions, key=lambda x: x.get("date", ""))

        # Filtrage des sessions valides
        filtered_sessions = [s for s in sessions if s.get("resultat") not in (None, "", "n/a")]
        if not filtered_sessions:
            await ctx.send(f"Aucune donnée valide pour {user_name}.")
            continue

        results = [parse_float(s.get("resultat", 0)) for s in filtered_sessions]
        erreurs = [safe_int(s.get("erreur")) or 0 for s in filtered_sessions]
        call_mucks = [safe_int(s.get("call_muck")) or 0 for s in filtered_sessions]
        dates = [s.get("date", "n/a") for s in filtered_sessions]

        # Résultats cumulés
        cum = []
        running = 0
        for r in results:
            running += r
            cum.append(running)

        x = np.arange(len(dates))  # positions X

        # --- GRAPHIQUE ---
        fig, ax1 = plt.subplots(figsize=(12, 6))

        # Axe gauche : résultats cumulés (DTS)
        color = "tab:blue"
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Résultats cumulés (DTS)", color=color)
        ax1.plot(x, cum, color=color, marker="o", label="Résultats cumulés (DTS)")
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.set_xticks(x)
        ax1.set_xticklabels(dates, rotation=45, ha='right')

        # Axe droit : erreurs + call muck sous forme de colonnes
        ax2 = ax1.twinx()
        ax2.set_ylabel("Erreurs / Call muck", color="gray")

        width = 0.35  # largeur des barres
        ax2.bar(x - width/2, erreurs, width, color="red", alpha=0.6, label="Erreurs grossières")
        ax2.bar(x + width/2, call_mucks, width, color="orange", alpha=0.6, label="Call muck")

        # Ajustement de l'échelle du second axe
        max_val = max(erreurs + call_mucks) if (erreurs + call_mucks) else 10
        ax2.set_ylim(0, max(max_val + 1, 10))
        ax2.tick_params(axis='y', labelcolor="gray")

        # Espacement automatique des dates
        if len(dates) > 10:
            step = max(1, len(dates) // 8)
            ax1.xaxis.set_major_locator(ticker.MultipleLocator(step))

        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper left")
        ax2.legend(loc="upper right")
        fig.tight_layout()

        img_path = f"stats_{user_id}.png"
        plt.savefig(img_path)
        plt.close()

        # Moyennesmoyennes en ignorant les "n/a" ---
        erreurs_raw = [safe_int(s.get("erreur")) for s in filtered_sessions]
        call_mucks_raw = [safe_int(s.get("call_muck")) for s in filtered_sessions]
        valid_erreurs = [e for e in erreurs_raw if e is not None]
        valid_call_mucks = [c for c in call_mucks_raw if c is not None]

        avg_erreur = (sum(valid_erreurs) / len(valid_erreurs)) if valid_erreurs else 0
        avg_call_muck = (sum(valid_call_mucks) / len(valid_call_mucks)) if valid_call_mucks else 0
        total = sum(results)
        avg_result = total / len(filtered_sessions)

        summary = (
            f"**👤 {user_name}**\n"
            f"- Sessions : {len(filtered_sessions)}\n"
            f"- Résultat total : {total:.2f} DTS\n"
            f"- Résultat moyen : {avg_result:.2f} DTS / session\n"
            f"- Erreurs grossières moyennes : {avg_erreur:.1f} (n={len(valid_erreurs)})\n"
            f"- Call muck moyen : {avg_call_muck:.1f} (n={len(valid_call_mucks)})\n"
        )

        await ctx.send(summary)
        await ctx.send(file=discord.File(img_path))
    
if __name__ == "__main__":
    if not TOKEN:
        print("Erreur: ajoute DISCORD_TOKEN dans .env")
    else:
        bot.run(TOKEN)