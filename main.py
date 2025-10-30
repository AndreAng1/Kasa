import streamlit as st
from supabase import create_client
from fpdf import FPDF
from io import BytesIO
from datetime import datetime
import pandas as pd

# ==========================================================
# 🔗 Connexion à Supabase
# ==========================================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================================================
# 🧾 Classe PDF
# ==========================================================
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "KASA", ln=True, align="C")

    def chapter_title(self, title):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, title, ln=True, align="L")

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


# ==========================================================
# ☁️ Upload du PDF dans Supabase Storage
# ==========================================================
def sanitize_filename(name):
    invalid_chars = [' ', '/', '\\', '?', '%', '*', ':', '|', '"', '<', '>', "'", 'é', 'è', 'ê', 'à']
    for c in invalid_chars:
        name = name.replace(c, "_")
    return name


def upload_pdf_to_supabase(file_bytes, filename, user_id):
    filename = sanitize_filename(filename)
    path = f"{user_id}/{filename}"
    response = supabase.storage.from_("kasa_storage").upload(
        path, file_bytes, {"content-type": "application/pdf", "x-upsert": "true"}
    )
    if response.get("error"):
        raise Exception(response["error"]["message"])
    public_url = supabase.storage.from_("kasa_storage").get_public_url(path)
    return public_url


# ==========================================================
# 🔐 Authentification Supabase Auth
# ==========================================================
if "user" not in st.session_state:
    st.session_state.user = None


def signup():
    """Création de compte"""
    st.subheader("Créer un compte KASA 🏠")
    nom = st.text_input("Nom", key="signup_nom")
    prenom = st.text_input("Prénom", key="signup_prenom")
    email = st.text_input("Email", key="signup_email")
    password = st.text_input("Mot de passe", type="password", key="signup_pwd")

    if st.button("Créer mon compte"):
        if not all([nom, prenom, email, password]):
            st.error("Tous les champs sont obligatoires.")
            return

        try:
            auth_response = supabase.auth.sign_up({"email": email, "password": password})

            if auth_response.user is None:
                st.error("Échec de la création du compte.")
                return

            user_id = auth_response.user.id

            # Insérer les infos supplémentaires dans la table utilisateurs
            supabase.table("utilisateurs").insert({
                "id": user_id,
                "nom": nom,
                "prenom": prenom
            }).execute()

            st.success("✅ Compte créé avec succès ! Vérifiez votre email pour valider votre compte.")
        except Exception as e:
            st.error(f"Erreur : {e}")


def login():
    """Connexion"""
    st.subheader("Connexion à KASA 🔑")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Mot de passe", type="password", key="login_pwd")

    if st.button("Se connecter"):
        try:
            auth_response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if auth_response.user is None:
                st.error("Identifiants incorrects.")
                return

            user = auth_response.user
            infos = supabase.table("utilisateurs").select("*").eq("id", user.id).execute().data
            info_user = infos[0] if infos else {}

            st.session_state.user = {
                "id": user.id,
                "email": user.email,
                "nom": info_user.get("nom", ""),
                "prenom": info_user.get("prenom", "")
            }

            st.success(f"Bienvenue, {info_user.get('prenom', user.email)} 👋")
            st.rerun()

        except Exception as e:
            st.error(f"Erreur de connexion : {e}")


def logout():
    """Déconnexion"""
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.success("Déconnecté ✅")
    st.rerun()


def afficher_auth():
    """Onglets de connexion / inscription"""
    if not st.session_state.user:
        tabs = st.tabs(["Connexion", "Créer un compte"])
        with tabs[0]:
            login()
        with tabs[1]:
            signup()
        return False
    else:
        user = st.session_state.user
        st.sidebar.success(f"Connecté : {user['email']}")
        if st.sidebar.button("Déconnexion"):
            logout()
        return True


# ==========================================================
# 🏠 PAGE D’ACCUEIL
# ==========================================================
def accueil():
    st.title("🏠 Bienvenue sur KASA")
    st.markdown("""
        ### Votre application de gestion locative intelligente

        KASA vous aide à :
        - Gérer vos **biens immobiliers**
        - Suivre vos **paiements de loyers**
        - Générer automatiquement vos **quittances PDF**
        - Accéder à un **tableau de bord clair** de vos revenus locatifs

        ---
        🔑 Cliquez ci-dessous pour vous connecter ou créer un compte :
    """)
    if st.button("➡️ Accéder à mon espace"):
        st.session_state["page"] = "auth"
        st.rerun()


# ==========================================================
# 🧭 INTERFACE UTILISATEUR
# ==========================================================
def interface_kasa
