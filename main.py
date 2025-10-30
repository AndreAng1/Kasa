import streamlit as st
from supabase import create_client
from fpdf import FPDF
import bcrypt
import uuid
from io import BytesIO
from datetime import datetime
import pandas as pd

# =========================
# ⚙️ Connexion Supabase
# =========================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# 📄 Classe PDF
# =========================
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
    safe_filename = filename.replace(" ", "_").replace("é", "e")
    path = f"{user_id}/{safe_filename}"
    response = supabase.storage.from_("kasa_storage").upload(
        path,
        file_bytes,
        {"content-type": "application/pdf", "x-upsert": "true"}
    )
    if response.get("error"):
        raise Exception(response["error"]["message"])
    return supabase.storage.from_("kasa_storage").get_public_url(path)

# =========================
# 🔐 Authentification
# =========================
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "Accueil"


def signup():
    st.subheader("Créer un compte")
    nom = st.text_input("Nom", key="nom")
    prenom = st.text_input("Prénom", key="prenom")
    email = st.text_input("Email", key="signup_email")
    password = st.text_input("Mot de passe", type="password", key="signup_pwd")

    if st.button("Créer mon compte"):
        if not all([nom, prenom, email, password]):
            st.error("Tous les champs sont obligatoires.")
            return
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        try:
            supabase.table("utilisateurs").insert({
                "id": str(uuid.uuid4()),
                "nom": nom,
                "prenom": prenom,
                "email": email,
                "mot_de_passe": hashed
            }).execute()
            st.success("Compte créé, connectez-vous.")
        except Exception as e:
            st.error(f"Erreur : {e}")


def login():
    st.subheader("Connexion")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Mot de passe", type="password", key="login_pwd")
    if st.button("Se connecter"):
        res = supabase.table("utilisateurs").select("*").eq("email", email).execute()
        user_data = res.data
        if user_data:
            user = user_data[0]
            if bcrypt.checkpw(password.encode("utf-8"), user["mot_de_passe"].encode("utf-8")):
                st.session_state.user = user
                st.success("Connecté avec succès ✅")
                st.session_state.page = "Application"
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
        else:
            st.error("Utilisateur introuvable.")


def logout():
    st.session_state.user = None
    st.session_state.page = "Accueil"
    st.success("Déconnecté ✅")
    st.rerun()


# =========================
# 🏠 PAGE D'ACCUEIL
# =========================
if st.session_state.page == "Accueil":
    st.title("🏡 Bienvenue sur KASA")
    st.markdown("""
    **KASA** est votre assistant intelligent pour la gestion locative.  
    Générez automatiquement vos contrats, suivez vos paiements et recevez vos quittances en un clic.

    ---
    ### 💡 Fonctionnalités principales :
    - Ajoutez et gérez vos **biens immobiliers**  
    - Suivez vos **paiements de loyers** avec génération automatique de quittances PDF  
    - Consultez vos **statistiques locatives** sur un tableau de bord clair et interactif  

    ---
    """)
    if st.button("🚀 Accéder à l'application"):
        st.session_state.page = "Authentification"
        st.rerun()

# =========================
# 🔑 PAGE D’AUTHENTIFICATION
# =========================
elif st.session_state.page == "Authentification" and not st.session_state.user:
    st.image("https://cdn-icons-png.flaticon.com/512/2950/2950657.png", width=100)
    st.title("🔐 Espace utilisateur KASA")
    tabs = st.tabs(["Connexion", "Créer un compte"])
    with tabs[0]:
        login()
    with tabs[1]:
        signup()

# =========================
# 💼 APPLICATION KASA
# =========================
elif st.session_state.user:
    user = st.session_state.user
    st.sidebar.success(f"Connecté : {user['email']}")
    if st.sidebar.button("Déconnexion"):
        logout()

    menu = st.sidebar.selectbox("Menu", ["🏘️ Ajouter un bien", "💳 Suivi des loyers", "📊 Tableau de bord"])

    # Ajouter un bien
    if menu == "🏘️ Ajouter un bien":
        st.header("Ajouter un bien")
        nom = st.text_input("Nom du bien")
        adresse = st.text_input("Adresse")
        superficie = st.number_input("Superficie", min_value=10.0)
        chambres = st.number_input("Chambres", 0)
        salon = st.number_input("Salons", 0)
        cuisine = st.number_input("Cuisines", 0)

        if st.button("Enregistrer bien"):
            supabase.table("biens").insert({
                "utilisateur_id": user["id"],
                "nom": nom,
                "adresse": adresse,
                "superficie": superficie,
                "chambres": chambres,
                "salon": salon,
                "cuisine": cuisine
            }).execute()
            st.success("Bien enregistré.")

    # Suivi des loyers
    elif menu == "💳 Suivi des loyers":
        st.header("Suivi des loyers")
        biens = supabase.table("biens").select("*").eq("utilisateur_id", user["id"]).execute().data
        if not biens:
            st.warning("Ajoutez d'abord un bien.")
        else:
            bien_dict = {b['nom']: b['id'] for b in biens}
            bien_nom = st.selectbox("Bien", list(bien_dict.keys()))
            locataire = st.text_input("Locataire")
            mois = st.selectbox("Mois", [
                "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
            ])
            annee = st.number_input("Année", min_value=2000, value=datetime.today().year)
            montant = st.number_input("Montant", min_value=0)
            statut = st.selectbox("Statut", ["Payé", "Non payé"])

            if st.button("Enregistrer paiement"):
                quittance_txt = f"""
QUITTANCE DE LOYER

Je soussigné, {user['prenom']} {user['nom']}, propriétaire du logement situé à :
{biens[0]['adresse']},

reconnais avoir reçu de :
{locataire},

la somme de {montant} FCFA au titre du loyer du mois de {mois} {annee}.

Fait à {biens[0]['adresse']}, le {datetime.today().strftime('%d/%m/%Y')}

Signature du bailleur : {user['prenom']} {user['nom']}
"""
                pdf = generate_pdf(quittance_txt)
                filename = f"quittance_{mois}_{annee}_{locataire}.pdf"
                url = upload_pdf_to_supabase(pdf.getvalue(), filename, user["id"])

                supabase.table("paiements").insert({
                    "contrat_id": None,
                    "mois": mois,
                    "annee": annee,
                    "montant": montant,
                    "statut": statut,
                    "quittance_url": url
                }).execute()

                st.success("Paiement enregistré.")
                st.download_button("📥 Télécharger quittance", pdf, file_name=filename)

    # Tableau de bord
    elif menu == "📊 Tableau de bord":
        st.header("Tableau de bord")
        paiements = supabase.table("paiements").select("*").execute().data
        if paiements:
            df = pd.DataFrame(paiements)
            st.dataframe(df)
        else:
            st.info("Aucun paiement trouvé.")
