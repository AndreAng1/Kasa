import streamlit as st
from supabase import create_client
from fpdf import FPDF
from io import BytesIO
from datetime import datetime
import pandas as pd
import bcrypt

# --- Configuration Supabase ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Classe PDF pour quittances ---
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "KASA", ln=True, align="C")

    def chapter_title(self, title):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, title, 0, 1, "L")

    def chapter_body(self, body):
        self.set_font("Arial", "", 11)
        self.multi_cell(0, 10, body)

    def add_contract(self, title, body):
        self.add_page()
        self.chapter_title(title)
        self.chapter_body(body)


def generate_pdf(content):
    pdf = PDF()
    pdf.add_contract("Quittance de Loyer", content)
    return BytesIO(pdf.output(dest="S").encode("latin1"))


def upload_pdf_to_supabase(file_bytes, filename, user_id):
    path = f"{user_id}/{filename.replace(' ', '_')}"
    response = supabase.storage.from_("kasa_storage").upload(
        path, file_bytes,
        {"content-type": "application/pdf", "x-upsert": "true"}
    )
    if response.get("error"):
        raise Exception(response["error"]["message"])
    return supabase.storage.from_("kasa_storage").get_public_url(path)

# --- Initialisation de session ---
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "Accueil"

# --- Interface d'accueil ---
def accueil():
    st.title("🏠 Bienvenue sur KASA")
    st.markdown("""
    **KASA** est votre solution moderne de **gestion locative automatisée** :
    - 📄 Génération automatique de contrats  
    - 💰 Suivi et quittances de loyers  
    - ☁️ Stockage sécurisé dans le cloud  
    - 🔐 Authentification Supabase sécurisée  
    ---
    """)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Se connecter ➜"):
            st.session_state.page = "Connexion"
            st.rerun()
    with col2:
        if st.button("Créer un compte ✍️"):
            st.session_state.page = "Inscription"
            st.rerun()

# --- Authentification : Inscription ---
import time

def inscription():
    st.header("Créer un compte")
    with st.form("form_inscription"):
        email = st.text_input("Email")
        password = st.text_input("Mot de passe", type="password")
        nom = st.text_input("Nom")
        prenom = st.text_input("Prénom")
        submitted = st.form_submit_button("Créer mon compte")

    if submitted:
        if not email.strip() or not password.strip() or not nom.strip() or not prenom.strip():
            st.error("⚠️ Veuillez remplir tous les champs.")
            return

        try:
            # Étape 1 : création du compte dans Supabase Auth
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            user = auth_response.user

            if not user:
                st.error("Erreur : l'utilisateur n'a pas été créé. Vérifiez l'email.")
                return

            # Étape 2 : Attendre que l’utilisateur apparaisse dans auth.users
            time.sleep(2)  # pause 2 secondes pour être sûr que l'ID soit disponible

            # Étape 3 : Insérer dans la table 'utilisateurs'
            insert_response = supabase.table("utilisateurs").insert({
                "id": str(user.id),
                "nom": nom.strip(),
                "prenom": prenom.strip()
            }).execute()

            if insert_response.data:
                st.success("✅ Compte créé avec succès !")
                st.info("Vérifiez votre email avant de vous connecter.")
                st.session_state.page = "Connexion"
                st.rerun()
            else:
                st.warning("Compte créé, mais profil non ajouté (tentative échouée).")

        except Exception as e:
            st.error(f"❌ Erreur lors de la création du compte : {e}")

    if st.button("⬅️ Retour à l'accueil"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- Authentification : Connexion ---
def connexion():
    st.header("Connexion à KASA")
    email = st.text_input("Email")
    password = st.text_input("Mot de passe", type="password")

    if st.button("Se connecter"):
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            user = res.user
            if user:
                # Récupération du profil
                data = supabase.table("utilisateurs").select("*").eq("id", user.id).execute()
                if data.data:
                    profile = data.data[0]
                    st.session_state.user = {
                        "id": user.id,
                        "email": email,
                        "nom": profile.get("nom", ""),
                        "prenom": profile.get("prenom", "")
                    }
                    st.success("Connexion réussie ✅")
                    st.session_state.page = "KASA"
                    st.rerun()
                else:
                    st.error("Profil introuvable, contactez l’administrateur.")
            else:
                st.error("Identifiants incorrects.")
        except Exception as e:
            st.error(f"Erreur : {e}")

    if st.button("⬅️ Retour à l'accueil"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- Déconnexion ---
def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.page = "Accueil"
    st.success("Déconnecté ✅")
    st.rerun()

# --- Interface principale KASA ---
def interface_kasa():
    user = st.session_state.user
    st.sidebar.success(f"Connecté : {user['email']}")
    if st.sidebar.button("Déconnexion"):
        logout()

    menu = st.sidebar.selectbox("Menu", ["🏘️ Ajouter un bien", "💳 Suivi des loyers", "📊 Tableau de bord"])

    if menu == "🏘️ Ajouter un bien":
        st.header("Ajouter un bien")
        nom = st.text_input("Nom du bien")
        adresse = st.text_input("Adresse")
        superficie = st.number_input("Superficie", min_value=10.0)
        chambres = st.number_input("Chambres", 0)
        salon = st.number_input("Salons", 0)
        cuisine = st.number_input("Cuisines", 0)

        if st.button("Enregistrer le bien"):
            supabase.table("biens").insert({
                "utilisateur_id": user["id"],
                "nom": nom,
                "adresse": adresse,
                "superficie": superficie,
                "chambres": chambres,
                "salon": salon,
                "cuisine": cuisine
            }).execute()
            st.success("Bien ajouté avec succès 🏡")

    elif menu == "💳 Suivi des loyers":
        st.header("Suivi des loyers")
        biens = supabase.table("biens").select("*").eq("utilisateur_id", user["id"]).execute().data
        if not biens:
            st.warning("Ajoutez d'abord un bien avant d'enregistrer un paiement.")
        else:
            bien_dict = {b['nom']: b for b in biens}
            bien_nom = st.selectbox("Choisir un bien", list(bien_dict.keys()))
            locataire = st.text_input("Nom du locataire")
            mois = st.selectbox("Mois", ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"])
            annee = st.number_input("Année", min_value=2000, value=datetime.today().year)
            montant = st.number_input("Montant payé (FCFA)", min_value=0)
            statut = st.selectbox("Statut du paiement", ["Payé", "Non payé"])

            if st.button("Enregistrer paiement"):
                quittance_txt = f"""
QUITTANCE DE LOYER

Je soussigné, {user['prenom']} {user['nom']}, propriétaire du logement situé à :
{bien_dict[bien_nom]['adresse']},

reconnais avoir reçu de :
{locataire},

la somme de {montant} FCFA au titre du loyer du mois de {mois} {annee}.

Fait à {bien_dict[bien_nom]['adresse']}, le {datetime.today().strftime('%d/%m/%Y')}

Signature du bailleur : {user['prenom']} {user['nom']}
"""
                pdf = generate_pdf(quittance_txt)
                filename = f"quittance_{mois}_{annee}_{locataire}.pdf"
                try:
                    url = upload_pdf_to_supabase(pdf.getvalue(), filename, user["id"])
                    supabase.table("paiements").insert({
                        "contrat_id": None,
                        "mois": mois,
                        "annee": annee,
                        "montant": montant,
                        "statut": statut,
                        "quittance_url": url
                    }).execute()
                    st.success("Paiement enregistré ✅")
                    st.download_button("📥 Télécharger quittance", pdf, file_name=filename)
                except Exception as e:
                    st.error(f"Erreur lors de l'upload : {e}")

    elif menu == "📊 Tableau de bord":
        st.header("Tableau de bord")
        paiements = supabase.table("paiements").select("*").execute().data
        if paiements:
            df = pd.DataFrame(paiements)
            st.dataframe(df)
        else:
            st.info("Aucun paiement trouvé.")

# --- ROUTEUR PRINCIPAL ---
def main():
    if st.session_state.page == "Accueil":
        accueil()
    elif st.session_state.page == "Inscription":
        inscription()
    elif st.session_state.page == "Connexion":
        connexion()
    elif st.session_state.page == "KASA" and st.session_state.user:
        interface_kasa()
    else:
        st.session_state.page = "Accueil"
        st.rerun()

if __name__ == "__main__":
    main()
