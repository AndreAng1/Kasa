import streamlit as st
from supabase import create_client
from fpdf import FPDF
from io import BytesIO
from datetime import datetime, date
import pandas as pd
import re
import unicodedata

# ---------------------------
# Config Supabase (via secrets)
# ---------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------
# Helpers
# ---------------------------
def safe_text_for_pdf(s: str) -> str:
    """Normalise les quotes typographiques et caractères problématiques pour FPDF latin1."""
    if s is None:
        return ""
    # Normalize accents to composed form
    s = unicodedata.normalize("NFC", str(s))
    # Replace fancy quotes by straight ones
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    # remove characters not encodable in latin-1 by replacing them
    return s

def sanitize_filename(name: str) -> str:
    # remplace les caractères non autorisés pour storage keys
    name = re.sub(r"[\\/:\*\?\"<>\|]", "_", name)
    name = name.replace(" ", "_")
    return name

# ---------------------------
# PDF generation (FPDF, latin1 safe)
# ---------------------------
class PDF(FPDF):
    def header(self):
        # petit titre centré
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "KASA", ln=True, align="C")
        self.ln(4)

    def add_centered_watermark(self, text="KASA"):
        # watermark light gray centered
        self.set_text_color(200, 200, 200)
        self.set_font("Arial", "B", 40)
        # approximate center
        x = (self.w / 2) - 30
        y = (self.h / 2)
        try:
            self.text(x, y, text)
        except Exception:
            # ignore if encoding/placement fails
            pass
        self.set_text_color(0, 0, 0)
        self.set_font("Arial", "", 11)

    def add_paragraph(self, text):
        self.set_font("Arial", "", 11)
        self.multi_cell(0, 7, text)

def generate_pdf_bytes(content: str, title="Document KASA") -> BytesIO:
    # sanitize content for latin1
    content_safe = safe_text_for_pdf(content)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, title, ln=True)
    pdf.ln(4)
    pdf.add_centered_watermark("KASA")
    pdf.add_paragraph(content_safe)
    # return BytesIO of binary latin1 output
    out = pdf.output(dest="S").encode("latin-1", errors="replace")
    return BytesIO(out)

# ---------------------------
# Storage upload
# ---------------------------
def upload_pdf_to_supabase(file_bytes: bytes, filename: str, auth_user_id: str) -> str:
    """
    file_bytes: bytes or BytesIO.getvalue()
    filename: raw filename (will be sanitized)
    auth_user_id: must be the auth.users id (UUID) so RLS policies match
    returns public url string
    """
    if isinstance(file_bytes, BytesIO):
        data = file_bytes.getvalue()
    else:
        data = file_bytes

    safe_name = sanitize_filename(filename)
    path = f"{auth_user_id}/{safe_name}"
    # storage upload expects a bytes-like object
    resp = supabase.storage.from_("kasa_storage").upload(path, data, {
        "content-type": "application/pdf",
        "x-upsert": "true"
    })
    # storage3 may return dict with 'error' key on failure
    if isinstance(resp, dict) and resp.get("error"):
        raise Exception(resp["error"])
    # get public url
    public = supabase.storage.from_("kasa_storage").get_public_url(path)
    # public is a dict with 'publicUrl' or similar depending on client; normalize
    if isinstance(public, dict) and public.get("publicUrl"):
        return public["publicUrl"]
    # fallback if object
    return public

# ---------------------------
# Auth : uses Supabase Auth (auth.users) + table utilisateurs for profile
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "accueil"

def signup_ui():
    st.subheader("Créer un compte")
    nom = st.text_input("Nom", key="s_nom")
    prenom = st.text_input("Prénom", key="s_prenom")
    email = st.text_input("Email", key="s_email")
    password = st.text_input("Mot de passe", type="password", key="s_pwd")
    if st.button("Créer le compte", key="s_submit"):
        if not all([nom, prenom, email, password]):
            st.error("Tous les champs sont obligatoires.")
            return
        try:
            # create in Supabase Auth
            auth_res = supabase.auth.sign_up({"email": email, "password": password})
            # If sign_up requires confirm email, auth_res.user can be None in some libs when email confirmation required.
            if getattr(auth_res, "user", None) is None and isinstance(auth_res, dict) and auth_res.get("user") is None:
                # some clients return dict with 'status' etc.
                # attempt to retrieve user id from returned dict (if any)
                user_id = None
                if isinstance(auth_res, dict) and auth_res.get("data") and auth_res["data"].get("user"):
                    user_id = auth_res["data"]["user"]["id"]
                else:
                    # can't get user id: inform user to confirm email
                    st.success("Compte créé. Vérifiez votre email pour confirmer votre compte, puis connectez-vous.")
                    return
            else:
                user_id = auth_res.user.id if getattr(auth_res, "user", None) else None

            if user_id:
                # store profile in utilisateurs (id references auth.users.id)
                supabase.table("utilisateurs").insert({
                    "id": user_id,
                    "nom": nom,
                    "prenom": prenom
                }).execute()
                st.success("Compte créé et profil enregistré. Vérifiez votre e-mail si nécessaire.")
            else:
                st.success("Compte créé. Vérifiez votre e-mail si nécessaire.")
        except Exception as e:
            st.error(f"Erreur lors de la création du compte : {e}")

def login_ui():
    st.subheader("Connexion")
    email = st.text_input("Email", key="l_email")
    password = st.text_input("Mot de passe", type="password", key="l_pwd")
    if st.button("Se connecter", key="l_submit"):
        if not email or not password:
            st.error("Email et mot de passe requis.")
            return
        try:
            auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            # `auth_res.user` should contain the user object when success
            user_obj = getattr(auth_res, "user", None) or (auth_res.get("user") if isinstance(auth_res, dict) else None)
            if not user_obj:
                st.error("Échec d'authentification. Vérifiez vos identifiants.")
                return
            user_id = user_obj.id if hasattr(user_obj, "id") else user_obj.get("id")
            # fetch profile
            profil = supabase.table("utilisateurs").select("*").eq("id", user_id).execute()
            prof_data = profil.data[0] if profil.data else {}
            st.session_state.user = {
                "id": user_id,
                "email": user_obj.email if hasattr(user_obj, "email") else user_obj.get("email"),
                "nom": prof_data.get("nom", ""),
                "prenom": prof_data.get("prenom", "")
            }
            st.success("Connecté ✅")
            st.session_state.page = "app"
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur de connexion : {e}")

def logout_action():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.session_state.page = "accueil"
    st.success("Déconnecté.")
    st.experimental_rerun()

# ---------------------------
# Application interface (mes biens, contrats, loyers, tableau)
# ---------------------------
def interface_kasa():
    user = st.session_state.user
    st.sidebar.success(f"Connecté : {user.get('email')}")
    if st.sidebar.button("Déconnexion", key="btn_logout"):
        logout_action()

    menu = st.sidebar.selectbox("Menu", ["🏘️ Ajouter un bien", "📄 Générer contrat", "💳 Suivi des loyers", "📊 Tableau de bord"], key="menu_main")

    # --- Ajouter un bien ---
    if menu == "🏘️ Ajouter un bien":
        st.header("Ajouter un bien")
        nom_bien = st.text_input("Nom du bien", key="bien_nom")
        adresse = st.text_input("Adresse", key="bien_adresse")
        chambres = st.number_input("Chambres", min_value=0, key="bien_chambres")
        salon = st.number_input("Salons", min_value=0, key="bien_salon")
        cuisine = st.number_input("Cuisines", min_value=0, key="bien_cuisine")
        superficie = st.number_input("Superficie (m²)", min_value=1, value=50, key="bien_superficie")
        loyer = st.number_input("Loyer mensuel (FCFA)", min_value=0, value=0, key="bien_loyer")
        if st.button("Ajouter le bien", key="add_bien"):
            # insert into biens (utilisateur_id must match auth.users.id or your design)
            supabase.table("biens").insert({
                "utilisateur_id": user["id"],
                "nom": nom_bien,
                "adresse": adresse,
                "superficie": superficie,
                "chambres": chambres,
                "salon": salon,
                "cuisine": cuisine,
                "created_at": datetime.now().isoformat()
            }).execute()
            st.success("Bien ajouté ✅")

        # list existing biens with delete option
        st.markdown("### Vos biens")
        biens = supabase.table("biens").select("*").eq("utilisateur_id", user["id"]).execute().data
        if biens:
            for b in biens:
                st.write(f"- **{b.get('nom')}** — {b.get('adresse')}")
            # supprimer un bien
            to_delete = st.selectbox("Supprimer un bien (sélectionnez)", [b['nom'] for b in biens], key="del_bien_select")
            if st.button("Supprimer le bien", key="del_bien_btn"):
                # find id
                bid = next((b['id'] for b in biens if b['nom'] == to_delete), None)
                if bid:
                    supabase.table("biens").delete().eq("id", bid).execute()
                    st.success("Bien supprimé.")
                    st.experimental_rerun()
        else:
            st.info("Aucun bien enregistré.")

    # --- Générer contrat ---
    elif menu == "📄 Générer contrat":
        st.header("Générer un contrat de bail")
        biens = supabase.table("biens").select("*").eq("utilisateur_id", user["id"]).execute().data
        locataires = supabase.table("locataires").select("*").eq("utilisateur_id", user["id"]).execute().data
        if not biens:
            st.warning("Ajoutez au moins un bien avant de générer un contrat.")
        else:
            bien_map = {b['nom']: b for b in biens}
            selected_bien_name = st.selectbox("Choisir un bien", list(bien_map.keys()), key="contrat_bien")
            selected_bien = bien_map[selected_bien_name]

            nom_loc = st.text_input("Nom du locataire", key="contrat_loc_nom")
            adresse_loc = st.text_input("Adresse du locataire", key="contrat_loc_adresse")
            tel_loc = st.text_input("Téléphone locataire", key="contrat_loc_tel")
            email_loc = st.text_input("Email locataire", key="contrat_loc_email")
            duree = st.number_input("Durée (mois)", min_value=1, value=12, key="contrat_duree")
            date_deb = st.date_input("Date de début", value=date.today(), key="contrat_debut")
            date_fin = st.date_input("Date de fin", value=date.today(), key="contrat_fin")
            depot = st.number_input("Dépôt de garantie (FCFA)", min_value=0, key="contrat_depot")
            mode_paiement = st.selectbox("Mode de paiement", ["Espèces", "Mobile Money", "Virement bancaire"], key="contrat_mode")
            coordonnees = st.text_area("Coordonnées de paiement (détails)", key="contrat_coord")
            signature_b = st.checkbox("Signature bailleur (coché = signé)", key="contrat_sig_b")
            signature_l = st.checkbox("Signature locataire (coché = signé)", key="contrat_sig_l")

            if st.button("Générer contrat PDF", key="gen_contrat"):
                pieces = f"{selected_bien.get('chambres',0)} chambres, {selected_bien.get('salon',0)} salon(s), {selected_bien.get('cuisine',0)} cuisine(s)"
                content = f"""
CONTRAT DE BAIL D'HABITATION

Entre les soussignés :

Le Bailleur
Nom : {user.get('prenom','')} {user.get('nom','')}
Adresse : {safe_text_for_pdf(selected_bien.get('adresse',''))}
Téléphone : [A renseigner]
Email : {user.get('email','')}

Et

Le Locataire
Nom : {nom_loc}
Adresse actuelle : {adresse_loc}
Téléphone : {tel_loc}
Email : {email_loc}

1. Désignation du bien loué
Le bailleur loue au locataire le logement situé à :
{safe_text_for_pdf(selected_bien.get('adresse',''))}
Ce logement est composé de : {pieces}
Superficie approximative : {selected_bien.get('superficie','')} m²

2. Destination des lieux
Le logement est loué à usage exclusif d'habitation.

3. Durée du bail
Le présent contrat est conclu pour une durée de {duree} mois à compter du {date_deb.strftime('%d/%m/%Y')} et prendra fin le {date_fin.strftime('%d/%m/%Y')}.

4. Loyer
Loyer mensuel : {selected_bien.get('loyer','Non défini')} FCFA
Mode de paiement : {mode_paiement}
Coordonnées : {coordonnees}

5. Dépôt de garantie
{depot} FCFA

6. État des lieux
Un état des lieux d'entrée et de sortie sera réalisé et signé par les deux parties.

Fait à {safe_text_for_pdf(selected_bien.get('adresse',''))}, le {datetime.today().strftime('%d/%m/%Y')}

Signature du Bailleur : {'Signé' if signature_b else ''}
Signature du Locataire : {'Signé' if signature_l else ''}
"""
                pdf_bytes = generate_pdf_bytes(content, title="Contrat de bail")
                filename = f"contrat_{sanitize_filename(selected_bien_name)}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                try:
                    url = upload_pdf_to_supabase(pdf_bytes.getvalue(), filename, user["id"])
                except Exception as e:
                    st.error(f"Erreur upload quittance : {e}")
                    url = None

                # Optionnel : insert contract record in contrats table
                try:
                    # Insert locataire if provided (and not yet in locataires)
                    loc_id = None
                    if nom_loc:
                        # check existing
                        res_loc = supabase.table("locataires").select("*").eq("utilisateur_id", user["id"]).eq("nom", nom_loc).execute()
                        if res_loc.data:
                            loc_id = res_loc.data[0]['id']
                        else:
                            loc_id = str(uuid.uuid4())
                            supabase.table("locataires").insert({
                                "id": loc_id,
                                "utilisateur_id": user["id"],
                                "nom": nom_loc,
                                "email": email_loc,
                                "telephone": tel_loc
                            }).execute()

                    contrat_row = {
                        "id": str(uuid.uuid4()),
                        "bien_id": selected_bien['id'],
                        "locataire_id": loc_id,
                        "date_debut": date_deb.isoformat(),
                        "date_fin": date_fin.isoformat(),
                        "loyer_mensuel": selected_bien.get('loyer', None),
                        "depot": depot,
                        "mode_paiement": mode_paiement,
                        "created_at": datetime.now().isoformat()
                    }
                    supabase.table("contrats").insert(contrat_row).execute()
                except Exception as e:
                    # ne bloque pas si contrat non inséré
                    st.warning(f"Contrat non inséré en base : {e}")

                st.success("Contrat généré.")
                if url:
                    st.markdown(f"[Télécharger le contrat]({url})")
                    st.write("📌 URL publique :", url)

    # --- Suivi des loyers ---
    elif menu == "💳 Suivi des loyers":
        st.header("Suivi des loyers")
        biens = supabase.table("biens").select("*").eq("utilisateur_id", user["id"]).execute().data
        if not biens:
            st.warning("Ajoutez d'abord un bien.")
        else:
            bien_map = {b['nom']: b for b in biens}
            chosen_name = st.selectbox("Bien", list(bien_map.keys()), key="suivi_bien")
            chosen_bien = bien_map[chosen_name]
            locataire = st.text_input("Nom du locataire", key="suivi_loc")
            mois = st.selectbox("Mois", ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"], key="suivi_mois")
            annee = st.number_input("Année", min_value=2000, value=datetime.today().year, key="suivi_annee")
            montant = st.number_input("Montant payé (FCFA)", min_value=0, key="suivi_montant")
            statut = st.selectbox("Statut", ["Payé", "Non payé"], key="suivi_statut")

            if st.button("Enregistrer paiement", key="suivi_save"):
                # generate quittance pdf
                quittance_txt = f"""
QUITTANCE DE LOYER

Je soussigné, {user.get('prenom','')} {user.get('nom','')}, propriétaire du logement situé à :
{safe_text_for_pdf(chosen_bien.get('adresse',''))},

reconnais avoir reçu de :
{locataire},

la somme de {montant} FCFA au titre du loyer du mois de {mois} {annee}.

Fait à {safe_text_for_pdf(chosen_bien.get('adresse',''))}, le {datetime.today().strftime('%d/%m/%Y')}

Signature du bailleur : {user.get('prenom','')} {user.get('nom','')}
"""
                pdf_bytes = generate_pdf_bytes(quittance_txt, title="Quittance de loyer")
                filename = f"quittance_{mois}_{annee}_{sanitize_filename(locataire)}.pdf"
                try:
                    url = upload_pdf_to_supabase(pdf_bytes.getvalue(), filename, user["id"])
                except Exception as e:
                    st.error(f"Erreur upload quittance : {e}")
                    url = None

                # insert paiement row (contrat_id optional)
                try:
                    supabase.table("paiements").insert({
                        "id": str(uuid.uuid4()),
                        "contrat_id": None,
                        "mois": mois,
                        "annee": annee,
                        "montant": montant,
                        "statut": statut,
                        "quittance_url": url,
                        "created_at": datetime.now().isoformat()
                    }).execute()
                except Exception as e:
                    st.warning(f"Erreur insertion paiement : {e}")

                st.success("Paiement enregistré.")
                if url:
                    st.markdown(f"[Télécharger la quittance]({url})")
                    st.write("📌 URL publique :", url)

            # show existing payments for that bien (optional join on paiements)
            st.markdown("### Paiements récents")
            payments = supabase.table("paiements").select("*").execute().data
            if payments:
                df = pd.DataFrame(payments)
                st.dataframe(df)
            else:
                st.info("Aucun paiement enregistré.")

    # --- Tableau de bord ---
    elif menu == "📊 Tableau de bord":
        st.header("Tableau de bord")
        # show key stats: total paiements, total montant, paiements par statut
        payments = supabase.table("paiements").select("*").execute().data
        if payments:
            df = pd.DataFrame(payments)
            # metrics
            total = df['montant'].sum() if 'montant' in df.columns else 0
            st.metric("Total encaissé (FCFA)", f"{int(total)}")
            st.subheader("Paiements")
            st.dataframe(df)
            # simple chart: count by statut
            if 'statut' in df.columns:
                stats = df.groupby("statut").size().reset_index(name="nombre")
                st.bar_chart(stats.set_index("statut"))
            # list quittances stored in storage for this user
            st.subheader("Quittances (Stockées)")
            # retrieve files in storage is not directly exposed in client; if you store URLs in paiements.quittance_url you can show them:
            if 'quittance_url' in df.columns:
                for i, row in df.iterrows():
                    if row.get('quittance_url'):
                        st.markdown(f"- [{row.get('mois')} {row.get('annee')}]({row.get('quittance_url')})")
        else:
            st.info("Aucun paiement trouvé.")

# ---------------------------
# Routing / pages
# ---------------------------
def main():
    st.set_page_config(page_title="KASA - Gestion locative", page_icon="🏠", layout="wide")
    # header / top bar
    st.markdown("<h1 style='text-align:center'>KASA — Gestion automatisée des loyers</h1>", unsafe_allow_html=True)
    # simple navigation flow
    if st.session_state.page == "accueil":
        st.title("Bienvenue sur KASA")
        st.markdown("""
            KASA vous aide à gérer vos biens, contrats, paiements et quittances.
            """)
        if st.button("Accéder à l'authentification", key="go_auth"):
            st.session_state.page = "auth"
            st.experimental_rerun()
    elif st.session_state.page == "auth" and st.session_state.user is None:
        # show login/signup tabs
        col1, col2 = st.columns([2,1])
        with col1:
            st.info("Connectez-vous ou créez un compte pour accéder à votre espace KASA.")
            tabs = st.tabs(["Connexion", "Créer un compte"])
            with tabs[0]:
                login_ui()
            with tabs[1]:
                signup_ui()
        with col2:
            st.markdown("### Pourquoi KASA ?")
            st.markdown("- Génération automatique de contrats et quittances\n- Centralisation des paiements\n- Tableau de bord simple")
    else:
        # user must be set in session_state before accessing app
        if st.session_state.user is None:
            st.warning("Veuillez vous connecter.")
            # show auth quickly
            tabs = st.tabs(["Connexion", "Créer un compte"])
            with tabs[0]:
                login_ui()
            with tabs[1]:
                signup_ui()
        else:
            # app interface
            interface_kasa()

if __name__ == "__main__":
    main()
