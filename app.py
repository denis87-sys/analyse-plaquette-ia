import streamlit as st
import base64
import json
import re
import anthropic
from jinja2 import Template
from weasyprint import HTML

# Configuration de la page
st.set_page_config(page_title="Analyse IA Immobilière", page_icon="🏢", layout="centered")

# --- CONSTANTES (Prompt & HTML) ---
SYSTEM_PROMPT = """Ton prompt métier détaillé ici... (Le même qu'à l'étape précédente)"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <style>
        @page { size: A4; margin: 15mm; }
        body { font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.5; color: #333; }
        h1 { color: #1a365d; border-bottom: 2px solid #2b6cb0; padding-bottom: 10px; }
        .card { background: #f7fafc; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e2e8f0; }
        .red-flag { background: #fff5f5; border-left: 4px solid #e53e3e; padding: 10px; margin-bottom: 10px; }
        .badge { font-weight: bold; color: #c53030; }
    </style>
</head>
<body>
    <h1>Analyse du programme : {{ analyse_generale.nom_programme }}</h1>
    <p><strong>📍 Localisation :</strong> {{ analyse_generale.localisation }} | <strong>📅 Livraison :</strong> {{ analyse_generale.date_livraison }}</p>
    
    <div class="card">
        <h3>💰 Données Financières</h3>
        <p><strong>Prix :</strong> {{ "{:,.0f}".format(donnees_financieres.prix_total_euros) }} €</p>
        <p><strong>Prix au m² :</strong> {{ "{:,.0f}".format(donnees_financieres.prix_au_m2_euros) }} €/m²</p>
    </div>

    <h3>🚨 Points de Vigilance (Red Flags)</h3>
    {% for flag in red_flags %}
    <div class="red-flag">
        <span class="badge">[{{ flag.gravite }}] {{ flag.sujet }}</span> : {{ flag.description_detaillee }}
    </div>
    {% endfor %}
    
    <h3>📐 Analyse de l'agencement</h3>
    <ul>
        {% for pf in analyse_du_plan.points_forts_agencement %}<li>✅ {{ pf }}</li>{% endfor %}
        {% for pf in analyse_du_plan.points_faibles_agencement %}<li>❌ {{ pf }}</li>{% endfor %}
    </ul>
</body>
</html>
"""

# --- INTERFACE UTILISATEUR ---
st.title("🏢 Analyseur de Plaquette Immobilière (IA)")
st.write("Uploadez une plaquette commerciale (PDF) pour obtenir un audit automatique (Red Flags, Prix, Agencement).")

# Streamlit va chercher la clé de manière invisible dans son coffre-fort
api_key = st.secrets["ANTHROPIC_API_KEY"]

# Zone d'upload
uploaded_file = st.file_uploader("Chargez le PDF de la plaquette", type=["pdf"])

if uploaded_file:
    if st.button("Lancer l'analyse 🚀"):
        # st.spinner affiche une animation de chargement pendant l'exécution du bloc "with"
        with st.spinner("Analyse en cours par Claude 3.5 Sonnet (cela peut prendre 15 à 30 secondes)..."):
            try:
                # 1. Préparation du PDF
                pdf_bytes = uploaded_file.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                
                # 2. Appel à l'API Claude
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    temperature=0.1,
                    system=SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64}},
                            {"type": "text", "text": "Analyse ce document et renvoie uniquement le JSON valide."}
                        ]
                    }]
                )
                
                # 3. Extraction du JSON
                raw_text = response.content[0].text.strip()
                clean_json = re.search(r"\{.*\}", raw_text, re.DOTALL).group(0)
                donnees = json.loads(clean_json)
                
                # 4. Génération du PDF avec Jinja2 et WeasyPrint
                rendered_html = Template(HTML_TEMPLATE).render(**donnees)
                pdf_output = HTML(string=rendered_html).write_pdf()
                
                st.success("✅ Analyse terminée avec succès !")
                
                # 5. Bouton de téléchargement natif de Streamlit
                st.download_button(
                    label="📥 Télécharger le compte-rendu (PDF)",
                    data=pdf_output,
                    file_name=f"Analyse_{uploaded_file.name}",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"Une erreur s'est produite : {str(e)}")
elif uploaded_file and not api_key:
    st.warning("👈 Veuillez entrer votre clé API Anthropic dans la barre latérale pour continuer.")
