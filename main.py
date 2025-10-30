# ==============================
# 🔐 AUTHENTIFICATION AVEC SUPABASE AUTH
# ==============================

import streamlit as st
from supabase import create_client

# Connexion Supabase
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------------
# ⚙️ Gestion de la session utilisateur
# ------------------------------
if "user" not in st.session_state:
    st.session_state.user = None


def signup():
    """Création de compte via Supabase Auth"""
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
            # 🔹 Création du compte dans Supabase Auth
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            if auth_response.user is None:
                st.error("Échec de l'inscription. Vérifiez vos informations.")
                return

            user_id = auth_response.user.id

            # 🔹 Enregistrement des infos supplémentaires dans la table `utilisateurs`
            supabase.table("utilisateurs").insert({
                "id": user_id,
                "nom": nom,
                "prenom": prenom
            }).execute()

            st.success("✅ Compte créé avec succès ! Vérifiez votre e-mail avant de vous connecter.")
        except Exception as e:
            st.error(f"Erreur : {e}")


def login():
    """Connexion avec Supabase Auth"""
    st.subheader("Connexion à KASA 🔑")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Mot de passe", type="password", key="login_pwd")

    if st.button("Se connecter"):
        if not email or not password:
            st.warning("Veuillez saisir vos identifiants.")
            return

        try:
            # 🔹 Connexion via Supabase Auth
            auth_response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if auth_response.user is None:
                st.error("Identifiants incorrects.")
                return

            user = auth_response.user

            # 🔹 On peut récupérer les infos utilisateur personnalisées
            res = supabase.table("utilisateurs").select("*").eq("id", user.id).execute()
            infos = res.data[0] if res.data else {}

            # 🔹 Stockage de la session
            st.session_state.user = {
                "id": user.id,
                "email": user.email,
                "nom": infos.get("nom", ""),
                "prenom": infos.get("prenom", "")
            }

            st.success(f"Bienvenue, {infos.get('prenom', user.email)} 👋")
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


# ------------------------------
# 🧭 Interface principale d'accès
# ------------------------------
def afficher_auth():
    """Affiche les onglets de connexion/inscription si l'utilisateur n'est pas connecté"""
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
