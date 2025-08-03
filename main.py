# Sistema Ordini Interattivo - Aggiungi DOPO gli import e PRIMA delle classi

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
from datetime import datetime
import json
import os

# Classe per i bottoni del fornitore (DM)
class SupplierOrderView(discord.ui.View):
    def __init__(self, order_id: int, customer_id: int):
        super().__init__(timeout=604800)  # 7 giorni timeout
        self.order_id = order_id
        self.customer_id = customer_id

    @discord.ui.button(label='✅ Conferma Ordine', style=discord.ButtonStyle.green)
    async def confirm_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        try:
            # Verifica che l'ordine esista e sia pending
            cursor.execute('''
                SELECT o.customer_id, i.item_name, o.quantity, o.total_price, s.username
                FROM orders o
                JOIN inventory i ON o.item_id = i.id  
                JOIN suppliers s ON o.supplier_id = s.user_id
                WHERE o.id = ? AND o.supplier_id = ? AND o.status = 'pending'
            ''', (self.order_id, interaction.user.id))
            
            order_data = cursor.fetchone()
            if not order_data:
                await interaction.followup.send("❌ Ordine non trovato o già processato.", ephemeral=True)
                return
            
            customer_id, item_name, quantity, total_price, supplier_name = order_data
            
            # Aggiorna status a completed
            cursor.execute('''
                UPDATE orders 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (self.order_id,))
            
            conn.commit()
            
            # Aggiorna il messaggio del fornitore
            embed = discord.Embed(
                title="✅ Ordine Confermato!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Ordine #", value=self.order_id, inline=True)
            embed.add_field(name="Oggetto", value=f"{item_name} x{quantity}", inline=True)
            embed.add_field(name="Totale", value=f"{total_price:,} ¥", inline=True)
            embed.add_field(name="Status", value="✅ COMPLETATO", inline=False)
            embed.set_footer(text="Ordine completato con successo!")
            
            # Rimuovi i bottoni
            await interaction.edit_original_response(embed=embed, view=None)
            
            # Notifica il cliente
            try:
                customer = await bot.fetch_user(customer_id)
                customer_embed = discord.Embed(
                    title="✅ Il tuo ordine è stato completato!",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                customer_embed.add_field(name="Ordine #", value=self.order_id, inline=True)
                customer_embed.add_field(name="Oggetto", value=f"{item_name} x{quantity}", inline=True)
                customer_embed.add_field(name="Fornitore", value=supplier_name, inline=True)
                customer_embed.add_field(name="Totale", value=f"{total_price:,} ¥", inline=True)
                customer_embed.set_footer(text="Grazie per aver usato PokeMMO Marketplace!")
                
                await customer.send(embed=customer_embed)
                print(f"✅ Notifica completamento inviata al cliente {customer_id}")
                
            except Exception as e:
                print(f"❌ Errore notifica cliente: {e}")
            
        except Exception as e:
            print(f"❌ Errore conferma ordine: {e}")
            await interaction.followup.send("❌ Errore durante la conferma dell'ordine.", ephemeral=True)
            conn.rollback()
            
        finally:
            cursor.close()
            conn.close()

    @discord.ui.button(label='❌ Annulla Ordine', style=discord.ButtonStyle.red)
    async def cancel_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        try:
            # Verifica che l'ordine esista e sia pending
            cursor.execute('''
                SELECT o.customer_id, o.item_id, o.quantity, i.item_name, o.total_price, s.username
                FROM orders o
                JOIN inventory i ON o.item_id = i.id
                JOIN suppliers s ON o.supplier_id = s.user_id  
                WHERE o.id = ? AND o.supplier_id = ? AND o.status = 'pending'
            ''', (self.order_id, interaction.user.id))
            
            order_data = cursor.fetchone()
            if not order_data:
                await interaction.followup.send("❌ Ordine non trovato o già processato.", ephemeral=True)
                return
            
            customer_id, item_id, quantity, item_name, total_price, supplier_name = order_data
            
            # Annulla l'ordine
            cursor.execute('UPDATE orders SET status = \'cancelled\' WHERE id = ?', (self.order_id,))
            
            # Ripristina l'inventario
            cursor.execute('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', (quantity, item_id))
            
            conn.commit()
            
            # Aggiorna il messaggio del fornitore
            embed = discord.Embed(
                title="❌ Ordine Annullato",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Ordine #", value=self.order_id, inline=True)
            embed.add_field(name="Oggetto", value=f"{item_name} x{quantity}", inline=True)
            embed.add_field(name="Status", value="❌ ANNULLATO", inline=False)
            embed.add_field(name="Inventario", value="✅ Quantità ripristinata", inline=False)
            embed.set_footer(text="Ordine annullato dal fornitore")
            
            await interaction.edit_original_response(embed=embed, view=None)
            
            # Notifica il cliente
            try:
                customer = await bot.fetch_user(customer_id)
                customer_embed = discord.Embed(
                    title="❌ Il tuo ordine è stato annullato",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                customer_embed.add_field(name="Ordine #", value=self.order_id, inline=True)
                customer_embed.add_field(name="Oggetto", value=f"{item_name} x{quantity}", inline=True)
                customer_embed.add_field(name="Fornitore", value=supplier_name, inline=True)
                customer_embed.add_field(name="Motivo", value="Annullato dal fornitore", inline=False)
                customer_embed.set_footer(text="L'oggetto è tornato disponibile nel catalogo")
                
                await customer.send(embed=customer_embed)
                print(f"✅ Notifica annullamento inviata al cliente {customer_id}")
                
            except Exception as e:
                print(f"❌ Errore notifica cliente: {e}")
            
        except Exception as e:
            print(f"❌ Errore annullamento ordine: {e}")
            await interaction.followup.send("❌ Errore durante l'annullamento dell'ordine.", ephemeral=True)
            conn.rollback()
            
        finally:
            cursor.close()
            conn.close()

# Classe per i bottoni del cliente
class CustomerOrderView(discord.ui.View):
    def __init__(self, order_id: int, supplier_id: int):
        super().__init__(timeout=604800)  # 7 giorni timeout
        self.order_id = order_id
        self.supplier_id = supplier_id

    @discord.ui.button(label='❌ Annulla Ordine', style=discord.ButtonStyle.red)
    async def cancel_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        try:
            # Verifica che l'ordine appartenga al cliente e sia pending
            cursor.execute('''
                SELECT o.supplier_id, o.item_id, o.quantity, i.item_name, o.total_price, s.username
                FROM orders o
                JOIN inventory i ON o.item_id = i.id
                JOIN suppliers s ON o.supplier_id = s.user_id
                WHERE o.id = ? AND o.customer_id = ? AND o.status = 'pending'
            ''', (self.order_id, interaction.user.id))
            
            order_data = cursor.fetchone()
            if not order_data:
                await interaction.followup.send("❌ Ordine non trovato o già processato.", ephemeral=True)
                return
            
            supplier_id, item_id, quantity, item_name, total_price, supplier_name = order_data
            
            # Annulla l'ordine
            cursor.execute('UPDATE orders SET status = \'cancelled\' WHERE id = ?', (self.order_id,))
            
            # Ripristina l'inventario
            cursor.execute('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', (quantity, item_id))
            
            conn.commit()
            
            # Conferma annullamento al cliente
            embed = discord.Embed(
                title="❌ Ordine Annullato",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Ordine #", value=self.order_id, inline=True)
            embed.add_field(name="Oggetto", value=f"{item_name} x{quantity}", inline=True)
            embed.add_field(name="Fornitore", value=supplier_name, inline=True)
            embed.add_field(name="Status", value="❌ ANNULLATO", inline=False)
            embed.set_footer(text="Ordine annullato con successo")
            
            await interaction.edit_original_response(embed=embed, view=None)
            
            # Notifica il fornitore
            try:
                supplier = await bot.fetch_user(supplier_id)
                supplier_embed = discord.Embed(
                    title="❌ Ordine annullato dal cliente",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                supplier_embed.add_field(name="Ordine #", value=self.order_id, inline=True)
                supplier_embed.add_field(name="Oggetto", value=f"{item_name} x{quantity}", inline=True)
                supplier_embed.add_field(name="Cliente", value=interaction.user.display_name, inline=True)
                supplier_embed.add_field(name="Inventario", value="✅ Quantità ripristinata automaticamente", inline=False)
                supplier_embed.set_footer(text="L'oggetto è tornato disponibile nel tuo inventario")
                
                await supplier.send(embed=supplier_embed)
                print(f"✅ Notifica annullamento inviata al fornitore {supplier_id}")
                
            except Exception as e:
                print(f"❌ Errore notifica fornitore: {e}")
            
        except Exception as e:
            print(f"❌ Errore annullamento ordine: {e}")
            await interaction.followup.send("❌ Errore durante l'annullamento dell'ordine.", ephemeral=True)
            conn.rollback()
            
        finally:
            cursor.close()
            conn.close()

    # Comando per vedere ordini con bottoni (SOSTITUISCE il comando view_orders)
    @app_commands.command(name='ordini', description='Visualizza i tuoi ordini con opzioni di gestione')
    async def view_orders_interactive(self, interaction: discord.Interaction):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT o.id, i.item_name, o.quantity, o.total_price, o.location, 
                   o.delivery_time, o.status, s.username, o.created_at, o.supplier_id
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
        
        # Separa ordini pending dagli altri
        pending_orders = [order for order in orders if order[6] == 'pending']
        completed_orders = [order for order in orders if order[6] != 'pending']
        
        embeds = []
        views = []
        
        # Ordini pending con bottoni
        for order_id, item_name, qty, total, location, delivery_time, status, supplier, created, supplier_id in pending_orders:
            embed = discord.Embed(
                title=f"⏳ Ordine #{order_id} - IN ATTESA",
                color=discord.Color.orange(),
                timestamp=datetime.fromisoformat(created.replace('Z', '+00:00')) if 'Z' in created else datetime.now()
            )
            embed.add_field(name="Oggetto", value=f"{item_name} x{qty}", inline=True)
            embed.add_field(name="Totale", value=f"{total:,} ¥", inline=True)
            embed.add_field(name="Fornitore", value=supplier, inline=True)
            embed.add_field(name="Luogo", value=location, inline=True)
            embed.add_field(name="Orario", value=delivery_time, inline=True)
            embed.add_field(name="Status", value="⏳ In attesa", inline=True)
            embed.set_footer(text="Puoi annullare questo ordine usando il bottone sotto")
            
            view = CustomerOrderView(order_id, supplier_id)
            embeds.append(embed)
            views.append(view)
        
        # Ordini completati/annullati (solo visualizzazione)
        if completed_orders:
            history_embed = discord.Embed(
                title="📋 Storico Ordini",
                color=discord.Color.blue()
            )
            
            for order_id, item_name, qty, total, location, delivery_time, status, supplier, created, supplier_id in completed_orders[:5]:
                status_emoji = "✅" if status == "completed" else "❌" if status == "cancelled" else "⏳"
                value = (f"**Oggetto:** {item_name} x{qty}\n"
                        f"**Totale:** {total:,} ¥\n"
                        f"**Fornitore:** {supplier}\n"
                        f"**Status:** {status_emoji} {status.upper()}")
                
                history_embed.add_field(name=f"Ordine #{order_id}", value=value, inline=False)
            
            embeds.append(history_embed)
            views.append(None)
        
        # Invia i messaggi
        if not embeds:
            await interaction.response.send_message("📝 Non hai ordini attivi.", ephemeral=True)
            return
        
        # Primo messaggio
        await interaction.response.send_message(
            embed=embeds[0], 
            view=views[0], 
            ephemeral=True
        )
        
        # Messaggi aggiuntivi
        for i in range(1, len(embeds)):
            await interaction.followup.send(
                embed=embeds[i], 
                view=views[i], 
                ephemeral=True
            )
    
    # AGGIORNA anche il comando place_order per includere i bottoni nel DM del fornitore
    # Sostituisci la parte dell'invio DM nel place_order con questa:
    
    async def send_supplier_notification_with_buttons(order_id, supplier_id, supplier_name, item_name, quantita, total_price, luogo, orario, customer):
        """Invia notifica DM al fornitore con bottoni interattivi"""
        dm_sent = False
        dm_error = None
        
        try:
            print(f"🔍 DEBUG: Tentativo invio DM a fornitore ID: {supplier_id}")
            
            supplier = await bot.fetch_user(supplier_id)
            print(f"✅ DEBUG: Utente fetchato da API: {supplier.display_name} ({supplier.name})")
            
            supplier_embed = discord.Embed(
                title="🛒 Nuovo ordine ricevuto!",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            supplier_embed.add_field(name="Ordine #", value=order_id, inline=True)
            supplier_embed.add_field(name="Cliente", value=customer.display_name, inline=True)
            supplier_embed.add_field(name="Oggetto", value=f"{item_name} x{quantita}", inline=True)
            supplier_embed.add_field(name="Totale", value=f"{total_price:,} ¥", inline=True)
            supplier_embed.add_field(name="Luogo consegna", value=luogo, inline=True)
            supplier_embed.add_field(name="Orario richiesto", value=orario, inline=True)
            supplier_embed.add_field(name="Contatto Discord", value=f"<@{customer.id}>", inline=False)
            supplier_embed.set_footer(text="Usa i bottoni sotto per gestire l'ordine")
            
            # Crea i bottoni per il fornitore
            view = SupplierOrderView(order_id, customer.id)
            
            await supplier.send(embed=supplier_embed, view=view)
            dm_sent = True
            print(f"✅ DEBUG: DM con bottoni inviato con successo a {supplier.display_name}")
            
        except discord.NotFound:
            dm_error = "Utente non esistente su Discord"
            print(f"❌ DEBUG: Utente {supplier_id} non esiste su Discord")
            
        except discord.Forbidden:
            dm_error = "L'utente ha disabilitato i DM o ha bloccato il bot"
            print(f"❌ DEBUG: DM bloccati dall'utente {supplier_id} (Forbidden)")
            
        except discord.HTTPException as e:
            dm_error = f"Errore HTTP Discord: {e}"
            print(f"❌ DEBUG: Errore HTTP inviando DM: {e}")
            
        except Exception as e:
            dm_error = f"Errore generico: {e}"
            print(f"❌ DEBUG: Errore generico inviando DM: {e}")
        
        return dm_sent, dm_error

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
    

    @app_commands.command(name='aggiungi', description='Aggiungi o aggiorna un oggetto nel tuo inventario')
    @app_commands.describe(
        nome="Nome dell'oggetto",
        quantita="Quantità da aggiungere", 
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
        
        # Controlla se l'oggetto esiste già per questo fornitore
        cursor.execute('''
            SELECT id, quantity, price, description 
            FROM inventory 
            WHERE supplier_id = ? AND LOWER(item_name) = LOWER(?)
        ''', (interaction.user.id, nome))
        
        existing_item = cursor.fetchone()
        
        if existing_item:
            # Oggetto esiste già - chiedi cosa fare
            item_id, current_qty, current_price, current_desc = existing_item
            
            embed = discord.Embed(
                title="🔄 Oggetto già presente nell'inventario",
                color=discord.Color.orange()
            )
            embed.add_field(name="Oggetto", value=nome, inline=True)
            embed.add_field(name="Quantità attuale", value=current_qty, inline=True)
            embed.add_field(name="Prezzo attuale", value=f"{current_price:,} ¥", inline=True)
            
            if current_desc:
                embed.add_field(name="Descrizione attuale", value=current_desc, inline=False)
            
            embed.add_field(name="🔄 Azione", value="Aggiorno quantità e prezzo automaticamente", inline=False)
            
            # Aggiorna quantità e prezzo
            new_quantity = current_qty + quantita
            
            cursor.execute('''
                UPDATE inventory 
                SET quantity = ?, price = ?, description = ?
                WHERE id = ?
            ''', (new_quantity, prezzo, descrizione or current_desc, item_id))
            
            embed.add_field(name="✅ Risultato", value=f"**Nuova quantità:** {new_quantity}\n**Nuovo prezzo:** {prezzo:,} ¥", inline=False)
            
            action = "aggiornato"
            
        else:
            # Nuovo oggetto - crea entry
            cursor.execute('''
                INSERT INTO inventory (supplier_id, item_name, quantity, price, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (interaction.user.id, nome, quantita, prezzo, descrizione))
            
            embed = discord.Embed(
                title="✅ Nuovo oggetto aggiunto",
                color=discord.Color.green()
            )
            embed.add_field(name="Oggetto", value=nome, inline=True)
            embed.add_field(name="Quantità", value=quantita, inline=True)
            embed.add_field(name="Prezzo", value=f"{prezzo:,} ¥", inline=True)
            
            if descrizione:
                embed.add_field(name="Descrizione", value=descrizione, inline=False)
            
            action = "aggiunto"
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Aggiungi anche un comando specifico per aggiornare solo la quantità
    @app_commands.command(name='aggiorna', description='Aggiorna quantità o prezzo di un oggetto esistente')
    @app_commands.describe(
        item_id="ID dell'oggetto da aggiornare",
        quantita="Nuova quantità totale (opzionale)",
        prezzo="Nuovo prezzo (opzionale)"
    )
    async def update_item(self, interaction: discord.Interaction, item_id: int, quantita: int = None, prezzo: int = None):
        if quantita is None and prezzo is None:
            await interaction.response.send_message("❌ Devi specificare almeno quantità o prezzo da aggiornare!", ephemeral=True)
            return
        
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        # Verifica che l'oggetto appartenga al fornitore
        cursor.execute('''
            SELECT item_name, quantity, price FROM inventory 
            WHERE id = ? AND supplier_id = ?
        ''', (item_id, interaction.user.id))
        
        item_data = cursor.fetchone()
        if not item_data:
            await interaction.response.send_message("❌ Oggetto non trovato o non autorizzato.", ephemeral=True)
            conn.close()
            return
        
        item_name, current_qty, current_price = item_data
        
        # Prepara gli aggiornamenti
        updates = []
        values = []
        
        if quantita is not None:
            updates.append("quantity = ?")
            values.append(quantita)
        
        if prezzo is not None:
            updates.append("price = ?")
            values.append(prezzo)
        
        values.append(item_id)
        
        # Esegui aggiornamento
        cursor.execute(f'''
            UPDATE inventory SET {", ".join(updates)}
            WHERE id = ?
        ''', values)
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🔄 Oggetto aggiornato",
            color=discord.Color.blue()
        )
        embed.add_field(name="Oggetto", value=f"#{item_id} - {item_name}", inline=True)
        
        if quantita is not None:
            embed.add_field(name="Quantità", value=f"{current_qty} → {quantita}", inline=True)
        
        if prezzo is not None:
            embed.add_field(name="Prezzo", value=f"{current_price:,} ¥ → {prezzo:,} ¥", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Aggiungi comando per gestire duplicati esistenti
    @app_commands.command(name='unisci', description='Unisci oggetti duplicati nel tuo inventario')
    @app_commands.describe(nome="Nome dell'oggetto da unificare")
    async def merge_items(self, interaction: discord.Interaction, nome: str):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        # Trova tutti gli oggetti con lo stesso nome per questo fornitore
        cursor.execute('''
            SELECT id, quantity, price, description 
            FROM inventory 
            WHERE supplier_id = ? AND LOWER(item_name) = LOWER(?)
            ORDER BY id
        ''', (interaction.user.id, nome))
        
        duplicates = cursor.fetchall()
        
        if len(duplicates) <= 1:
            await interaction.response.send_message("❌ Non ci sono duplicati per questo oggetto.", ephemeral=True)
            conn.close()
            return
        
        # Calcola totali
        total_quantity = sum(item[1] for item in duplicates)
        latest_price = duplicates[-1][2]  # Usa il prezzo più recente
        latest_description = duplicates[-1][3] or ""  # Usa la descrizione più recente
        
        # Mantieni il primo ID, elimina gli altri
        keep_id = duplicates[0][0]
        delete_ids = [item[0] for item in duplicates[1:]]
        
        # Aggiorna il primo oggetto con i totali
        cursor.execute('''
            UPDATE inventory 
            SET quantity = ?, price = ?, description = ?
            WHERE id = ?
        ''', (total_quantity, latest_price, latest_description, keep_id))
        
        # Elimina i duplicati
        for delete_id in delete_ids:
            cursor.execute('DELETE FROM inventory WHERE id = ?', (delete_id,))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🔄 Oggetti unificati",
            color=discord.Color.green()
        )
        embed.add_field(name="Oggetto", value=nome, inline=True)
        embed.add_field(name="Quantità totale", value=total_quantity, inline=True)
        embed.add_field(name="Prezzo finale", value=f"{latest_price:,} ¥", inline=True)
        embed.add_field(name="Duplicati rimossi", value=len(delete_ids), inline=True)
        embed.add_field(name="ID mantenuto", value=f"#{keep_id}", inline=True)
        
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
        # IMPORTANTE: Risposta immediata per evitare timeout
        await interaction.response.defer(ephemeral=True)
        
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        try:
            # Verifica disponibilità oggetto
            cursor.execute('''
                SELECT i.supplier_id, i.item_name, i.quantity, i.price, s.username
                FROM inventory i
                JOIN suppliers s ON i.supplier_id = s.user_id
                WHERE i.id = ?
            ''', (item_id,))
            
            item_data = cursor.fetchone()
            if not item_data:
                await interaction.followup.send("❌ Oggetto non trovato.", ephemeral=True)
                return
            
            supplier_id, item_name, available_qty, price, supplier_name = item_data
            
            if quantita > available_qty:
                await interaction.followup.send(f"❌ Quantità non disponibile. Disponibili: {available_qty}", ephemeral=True)
                return
            
            if interaction.user.id == supplier_id:
                await interaction.followup.send("❌ Non puoi ordinare dai tuoi stessi oggetti!", ephemeral=True)
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
            
            # Invia notifica al fornitore CON BOTTONI
            dm_sent, dm_error = await send_supplier_notification_with_buttons(
                order_id, supplier_id, supplier_name, item_name, 
                quantita, total_price, luogo, orario, interaction.user
            )
            
            # Invia conferma al cliente CON BOTTONE ANNULLA
            embed = discord.Embed(
                title="✅ Ordine confermato!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Ordine #", value=order_id, inline=True)
            embed.add_field(name="Oggetto", value=f"{item_name} x{quantita}", inline=True)
            embed.add_field(name="Totale", value=f"{total_price:,} ¥", inline=True)
            embed.add_field(name="Fornitore", value=supplier_name, inline=True)
            embed.add_field(name="Luogo", value=luogo, inline=True)
            embed.add_field(name="Orario", value=orario, inline=True)
            
            # Aggiungi stato notifica
            if dm_sent:
                embed.add_field(name="📨 Notifica", value="✅ Fornitore notificato via DM", inline=False)
                embed.set_footer(text="Il fornitore ha ricevuto una notifica privata con bottoni di gestione")
            else:
                embed.add_field(name="📨 Notifica", value=f"❌ DM non inviato: {dm_error}", inline=False)
                embed.add_field(name="💡 Azione richiesta", value=f"Contatta <@{supplier_id}> manualmente per l'ordine", inline=False)
                embed.set_footer(text="Notifica DM fallita - contatto manuale necessario")
            
            # Aggiungi bottone annulla per il cliente
            view = CustomerOrderView(order_id, supplier_id)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            print(f"✅ DEBUG: Conferma ordine con bottoni inviata al cliente {interaction.user.display_name}")
            
        except Exception as e:
            print(f"❌ DEBUG: Errore generale nel comando ordina: {e}")
            try:
                await interaction.followup.send("❌ Errore durante la creazione dell'ordine. Riprova.", ephemeral=True)
            except:
                pass  # Se anche followup fallisce, non c'è niente da fare
            
            conn.rollback()
            
        finally:
            cursor.close()
            conn.close()
                
            

    


    # Comando per fornitori per vedere i loro ordini ricevuti
    @bot.tree.command(name='ordini_ricevuti', description='[FORNITORI] Visualizza ordini ricevuti dai clienti')
    async def view_received_orders(interaction: discord.Interaction):
        conn = sqlite3.connect('pokemmo_marketplace.db')
        cursor = conn.cursor()
        
        # Verifica che sia un fornitore registrato
        cursor.execute('SELECT user_id FROM suppliers WHERE user_id = ? AND active = TRUE', (interaction.user.id,))
        if not cursor.fetchone():
            await interaction.response.send_message("❌ Devi essere registrato come fornitore!", ephemeral=True)
            cursor.close()
            conn.close()
            return
        
        cursor.execute('''
            SELECT o.id, i.item_name, o.quantity, o.total_price, o.location, 
                   o.delivery_time, o.status, o.created_at, o.customer_id
            FROM orders o
            JOIN inventory i ON o.item_id = i.id
            WHERE o.supplier_id = ?
            ORDER BY o.created_at DESC
            LIMIT 15
        ''', (interaction.user.id,))
        
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            await interaction.response.send_message("📝 Non hai ancora ricevuto ordini.", ephemeral=True)
            return
        
        # Separa per status
        pending_orders = [order for order in orders if order[6] == 'pending']
        completed_orders = [order for order in orders if order[6] == 'completed']
        cancelled_orders = [order for order in orders if order[6] == 'cancelled']
        
        embeds = []
        
        # Ordini pending
        if pending_orders:
            pending_embed = discord.Embed(
                title="⏳ Ordini in Attesa",
                color=discord.Color.orange(),
                description=f"Hai {len(pending_orders)} ordini da gestire"
            )
            
            for order_id, item_name, qty, total, location, delivery_time, status, created, customer_id in pending_orders[:5]:
                try:
                    customer = bot.get_user(customer_id)
                    customer_name = customer.display_name if customer else f"User-{customer_id}"
                except:
                    customer_name = f"User-{customer_id}"
                
                value = (f"**Cliente:** {customer_name}\n"
                        f"**Oggetto:** {item_name} x{qty}\n"
                        f"**Totale:** {total:,} ¥\n"
                        f"**Luogo:** {location}\n"
                        f"**Orario:** {delivery_time}")
                
                pending_embed.add_field(name=f"Ordine #{order_id}", value=value, inline=False)
            
            pending_embed.set_footer(text="Gestisci gli ordini dai messaggi privati del bot")
            embeds.append(pending_embed)
        
        # Storico ordini completati
        if completed_orders:
            completed_embed = discord.Embed(
                title="✅ Ordini Completati",
                color=discord.Color.green(),
                description=f"Hai completato {len(completed_orders)} ordini"
            )
            
            total_earnings = sum(order[3] for order in completed_orders)
            completed_embed.add_field(
                name="💰 Guadagni Totali", 
                value=f"{total_earnings:,} ¥", 
                inline=False
            )
            
            embeds.append(completed_embed)
        
        # Ordini annullati
        if cancelled_orders:
            cancelled_embed = discord.Embed(
                title="❌ Ordini Annullati",
                color=discord.Color.red(),
                description=f"{len(cancelled_orders)} ordini annullati"
            )
            embeds.append(cancelled_embed)
        
        # Invia embeds
        await interaction.response.send_message(embed=embeds[0], ephemeral=True)
        
        for embed in embeds[1:]:
            await interaction.followup.send(embed=embed, ephemeral=True)

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
