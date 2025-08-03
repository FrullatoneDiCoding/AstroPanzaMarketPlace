import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
from datetime import datetime
import json
import os

# Configurazione bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Inizializzazione database
def init_db():
    conn = sqlite3.connect('pokemmo_marketplace.db')
    cursor = conn.cursor()
    
    # Tabella fornitori
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Tabella inventario
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL,
            description TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (user_id)
        )
    ''')
    
    # Tabella ordini
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            location TEXT NOT NULL,
            delivery_time TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES inventory (id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f'🎮 {bot.user} è online e pronto!')
    print(f'📊 Connesso a {len(bot.guilds)} server(s)')
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Sincronizzati {len(synced)} comandi slash.")
    except Exception as e:
        print(f"❌ Errore nella sincronizzazione: {e}")

# Gruppo comandi fornitore
class SupplierCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name='fornitore', description='Comandi per fornitori')

    @app_commands.command(name='registra', description='Registrati come fornitore')
    async def register_supplier(self, interaction: discord.Interaction):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        cursor.execute('INSERT OR REPLACE INTO suppliers (user_id, username) VALUES (?, ?)',
                      (interaction.user.id, interaction.user.display_name))
        conn.commit()
        conn.close()
        
        await interaction.response.send_message("✅ Ti sei registrato come fornitore!", ephemeral=True)

    @app_commands.command(name='aggiungi', description='Aggiungi un oggetto al tuo inventario')
    @app_commands.describe(
        nome="Nome dell'oggetto",
        quantita="Quantità disponibile", 
        prezzo="Prezzo per unità",
        descrizione="Descrizione opzionale"
    )
    async def add_item(self, interaction: discord.Interaction, nome: str, quantita: int, prezzo: int, descrizione: str = ""):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        # Verifica se è registrato come fornitore
        cursor.execute('SELECT user_id FROM suppliers WHERE user_id = ?', (interaction.user.id,))
        if not cursor.fetchone():
            await interaction.response.send_message("❌ Devi prima registrarti come fornitore!", ephemeral=True)
            conn.close()
            return
        
        cursor.execute('''
            INSERT INTO inventory (supplier_id, item_name, quantity, price, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (interaction.user.id, nome, quantita, prezzo, descrizione))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Oggetto aggiunto",
            color=discord.Color.green()
        )
        embed.add_field(name="Oggetto", value=nome, inline=True)
        embed.add_field(name="Quantità", value=quantita, inline=True)
        embed.add_field(name="Prezzo", value=f"{prezzo:,} ¥", inline=True)
        if descrizione:
            embed.add_field(name="Descrizione", value=descrizione, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='inventario', description='Visualizza il tuo inventario')
    async def view_inventory(self, interaction: discord.Interaction):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, item_name, quantity, price, description 
            FROM inventory 
            WHERE supplier_id = ? AND quantity > 0
            ORDER BY item_name
        ''', (interaction.user.id,))
        
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            await interaction.response.send_message("📦 Il tuo inventario è vuoto.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📦 Inventario di {interaction.user.display_name}",
            color=discord.Color.blue()
        )
        
        for item_id, name, qty, price, desc in items:
            value = f"**Quantità:** {qty}\n**Prezzo:** {price:,} ¥"
            if desc:
                value += f"\n**Descrizione:** {desc}"
            embed.add_field(name=f"#{item_id} - {name}", value=value, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='rimuovi', description='Rimuovi un oggetto dal tuo inventario')
    @app_commands.describe(item_id="ID dell'oggetto da rimuovere")
    async def remove_item(self, interaction: discord.Interaction, item_id: int):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM inventory WHERE id = ? AND supplier_id = ?', 
                      (item_id, interaction.user.id))
        
        if cursor.rowcount > 0:
            conn.commit()
            await interaction.response.send_message(f"✅ Oggetto #{item_id} rimosso dall'inventario.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Oggetto non trovato o non autorizzato.", ephemeral=True)
        
        conn.close()

# Gruppo comandi cliente
class CustomerCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name='negozio', description='Comandi per acquisti')

    @app_commands.command(name='catalogo', description='Visualizza tutti gli oggetti disponibili')
    async def view_catalog(self, interaction: discord.Interaction):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT i.id, i.item_name, i.quantity, i.price, i.description, s.username
            FROM inventory i
            JOIN suppliers s ON i.supplier_id = s.user_id
            WHERE i.quantity > 0
            ORDER BY i.item_name
        ''')
        
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            await interaction.response.send_message("🏪 Nessun oggetto disponibile al momento.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🏪 Catalogo PokeMMO Marketplace",
            color=discord.Color.gold()
        )
        
        for item_id, name, qty, price, desc, supplier in items:
            value = f"**Fornitore:** {supplier}\n**Disponibili:** {qty}\n**Prezzo:** {price:,} ¥"
            if desc:
                value += f"\n**Descrizione:** {desc}"
            embed.add_field(name=f"#{item_id} - {name}", value=value, inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='ordina', description='Effettua un ordine')
    @app_commands.describe(
        item_id="ID dell'oggetto da ordinare",
        quantita="Quantità da ordinare",
        luogo="Luogo di consegna (es. Vermilion City)",
        orario="Orario preferito (es. 20:00 o domani sera)"
    )
    async def place_order(self, interaction: discord.Interaction, item_id: int, quantita: int, luogo: str, orario: str):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        # Verifica disponibilità oggetto
        cursor.execute('''
            SELECT i.supplier_id, i.item_name, i.quantity, i.price, s.username
            FROM inventory i
            JOIN suppliers s ON i.supplier_id = s.user_id
            WHERE i.id = ?
        ''', (item_id,))
        
        item_data = cursor.fetchone()
        if not item_data:
            await interaction.response.send_message("❌ Oggetto non trovato.", ephemeral=True)
            conn.close()
            return
        
        supplier_id, item_name, available_qty, price, supplier_name = item_data
        
        if quantita > available_qty:
            await interaction.response.send_message(f"❌ Quantità non disponibile. Disponibili: {available_qty}", ephemeral=True)
            conn.close()
            return
        
        if interaction.user.id == supplier_id:
            await interaction.response.send_message("❌ Non puoi ordinare dai tuoi stessi oggetti!", ephemeral=True)
            conn.close()
            return
        
        total_price = price * quantita
        
        # Crea ordine
        cursor.execute('''
            INSERT INTO orders (customer_id, supplier_id, item_id, quantity, total_price, location, delivery_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (interaction.user.id, supplier_id, item_id, quantita, total_price, luogo, orario))
        
        order_id = cursor.lastrowid
        
        # Aggiorna inventario
        cursor.execute('UPDATE inventory SET quantity = quantity - ? WHERE id = ?', (quantita, item_id))
        
        conn.commit()
        conn.close()
        
        # Invia conferma al cliente
        embed = discord.Embed(
            title="✅ Ordine confermato!",
            color=discord.Color.green()
        )
        embed.add_field(name="Ordine #", value=order_id, inline=True)
        embed.add_field(name="Oggetto", value=f"{item_name} x{quantita}", inline=True)
        embed.add_field(name="Totale", value=f"{total_price:,} ¥", inline=True)
        embed.add_field(name="Fornitore", value=supplier_name, inline=True)
        embed.add_field(name="Luogo", value=luogo, inline=True)
        embed.add_field(name="Orario", value=orario, inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Invia notifica al fornitore
        try:
            supplier = bot.get_user(supplier_id)
            if supplier:
                supplier_embed = discord.Embed(
                    title="🛒 Nuovo ordine ricevuto!",
                    color=discord.Color.orange()
                )
                supplier_embed.add_field(name="Ordine #", value=order_id, inline=True)
                supplier_embed.add_field(name="Cliente", value=interaction.user.display_name, inline=True)
                supplier_embed.add_field(name="Oggetto", value=f"{item_name} x{quantita}", inline=True)
                supplier_embed.add_field(name="Totale", value=f"{total_price:,} ¥", inline=True)
                supplier_embed.add_field(name="Luogo consegna", value=luogo, inline=True)
                supplier_embed.add_field(name="Orario richiesto", value=orario, inline=True)
                supplier_embed.add_field(name="Contatto Discord", value=f"<@{interaction.user.id}>", inline=False)
                
                await supplier.send(embed=supplier_embed)
        except:
            pass  # Se non riesce a inviare DM al fornitore

    @app_commands.command(name='ordini', description='Visualizza i tuoi ordini')
    async def view_orders(self, interaction: discord.Interaction):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT o.id, i.item_name, o.quantity, o.total_price, o.location, 
                   o.delivery_time, o.status, s.username, o.created_at
            FROM orders o
            JOIN inventory i ON o.item_id = i.id
            JOIN suppliers s ON o.supplier_id = s.user_id
            WHERE o.customer_id = ?
            ORDER BY o.created_at DESC
            LIMIT 10
        ''', (interaction.user.id,))
        
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            await interaction.response.send_message("📝 Non hai ancora effettuato ordini.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📝 I tuoi ordini",
            color=discord.Color.purple()
        )
        
        for order_id, item_name, qty, total, location, delivery_time, status, supplier, created in orders:
            status_emoji = "⏳" if status == "pending" else "✅" if status == "completed" else "❌"
            value = (f"**Oggetto:** {item_name} x{qty}\n"
                    f"**Totale:** {total:,} ¥\n"
                    f"**Fornitore:** {supplier}\n"
                    f"**Luogo:** {location}\n"
                    f"**Orario:** {delivery_time}\n"
                    f"**Status:** {status_emoji} {status}")
            
            embed.add_field(name=f"Ordine #{order_id}", value=value, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Comandi di amministrazione
@bot.tree.command(name='stats', description='Statistiche del marketplace')
@app_commands.default_permissions(administrator=True)
async def marketplace_stats(interaction: discord.Interaction):
    conn = sqlite3.connect('pokemmo_marketplace.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM suppliers')
    total_suppliers = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM inventory WHERE quantity > 0')
    total_items = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM orders')
    total_orders = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(total_price) FROM orders')
    total_volume = cursor.fetchone()[0] or 0
    
    conn.close()
    
    embed = discord.Embed(
        title="📊 Statistiche Marketplace",
        color=discord.Color.dark_blue()
    )
    embed.add_field(name="Fornitori attivi", value=total_suppliers, inline=True)
    embed.add_field(name="Oggetti disponibili", value=total_items, inline=True)
    embed.add_field(name="Ordini totali", value=total_orders, inline=True)
    embed.add_field(name="Volume scambi", value=f"{total_volume:,} ¥", inline=True)
    
    await interaction.response.send_message(embed=embed)

# Registra i gruppi di comandi
bot.tree.add_command(SupplierCommands())
bot.tree.add_command(CustomerCommands())

# Comando di aiuto
@bot.tree.command(name='aiuto', description='Mostra tutti i comandi disponibili')
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 PokeMMO Marketplace Bot - Guida",
        description="Sistema di marketplace per la tua gilda PokeMMO",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="👤 Comandi Fornitore",
        value=(
            "`/fornitore registra` - Registrati come fornitore\n"
            "`/fornitore aggiungi` - Aggiungi oggetto all'inventario\n"
            "`/fornitore inventario` - Visualizza il tuo inventario\n"
            "`/fornitore rimuovi` - Rimuovi oggetto dall'inventario"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛒 Comandi Cliente",
        value=(
            "`/negozio catalogo` - Visualizza tutti gli oggetti\n"
            "`/negozio ordina` - Effettua un ordine\n"
            "`/negozio ordini` - Visualizza i tuoi ordini"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Funzionalità",
        value=(
            "• Inventario automatico con quantità\n"
            "• Notifiche private ai fornitori\n"
            "• Gestione ordini con luogo e orario\n"
            "• Riduzione automatica delle scorte\n"
            "• Sistema di tracking ordini"
        ),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# Health check per Railway
@bot.event
async def on_connect():
    print("🔗 Bot connesso a Discord!")

# Avvia il bot
if __name__ == "__main__":
    # Prende il token dalle variabili d'ambiente
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ ERRORE: Token Discord non trovato!")
        print("Assicurati di aver impostato la variabile DISCORD_TOKEN in Railway")
        exit(1)
    
    print("🚀 Avvio bot...")
    bot.run(TOKEN)
