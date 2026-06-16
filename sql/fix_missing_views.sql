
-- ============================================================
--  RATTRAPAGE VUES MANQUANTES + VÉRIFICATION BRIDGE
-- ============================================================

-- 1. Vérifier si bridge_offre_competence est remplie
SELECT 'bridge_offre_competence' AS objet, COUNT(*) AS nb_lignes FROM bridge_offre_competence;


-- 2. Si bridge est vide, la remplir (au cas où l'INSERT n'a pas tourné)
--    (Si elle est déjà remplie, cette requête n'insérera rien grâce à ON CONFLICT)
INSERT INTO bridge_offre_competence (offre_id, competence_id, source_champ)
SELECT DISTINCT f.offre_id, c.competence_id, 'description'
FROM fact_offres f
CROSS JOIN dim_competence c
WHERE (
    f.description ILIKE '%' || c.nom || '%'
    OR f.titre ILIKE '%' || c.nom || '%'
    OR f.description ILIKE '%' || LOWER(c.nom) || '%'
    OR f.titre ILIKE '%' || LOWER(c.nom) || '%'
)
ON CONFLICT (offre_id, competence_id) DO NOTHING;


-- 3. Recréer vw_competences_top
DROP VIEW IF EXISTS vw_competences_top;

CREATE OR REPLACE VIEW vw_competences_top AS
SELECT
    c.nom AS competence,
    c.categorie,
    COUNT(DISTINCT b.offre_id) AS nb_offres,
    ROUND(100.0 * COUNT(DISTINCT b.offre_id) / NULLIF((SELECT COUNT(*) FROM fact_offres), 0), 1) AS pct_offres,
    ROUND(AVG(f.salaire_min)::numeric, 0) AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0) AS salaire_moyen_max,
    ROUND(AVG(f.salaire_predit_eur)::numeric, 0) AS salaire_predit_moyen
FROM bridge_offre_competence b
JOIN dim_competence c ON b.competence_id = c.competence_id
LEFT JOIN fact_offres f ON b.offre_id = f.offre_id
GROUP BY c.nom, c.categorie
ORDER BY nb_offres DESC;


-- 4. Recréer vw_offre_competences_flat
DROP VIEW IF EXISTS vw_offre_competences_flat;

CREATE OR REPLACE VIEW vw_offre_competences_flat AS
SELECT
    b.offre_id,
    f.titre,
    f.rome_libelle AS metier,
    f.source,
    f.type_contrat,
    f.experience,
    c.nom AS competence,
    c.categorie,
    f.salaire_min,
    f.salaire_max,
    f.salaire_predit_eur,
    f.salaire_confiance,
    l.ville,
    l.pays,
    e.nom AS entreprise,
    e.secteur
FROM bridge_offre_competence b
JOIN dim_competence c ON b.competence_id = c.competence_id
JOIN fact_offres f ON b.offre_id = f.offre_id
LEFT JOIN dim_lieu l ON f.lieu_id = l.lieu_id
LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id;


-- 5. VÉRIFICATION FINALE
SELECT '=== VUES DISPONIBLES ===' AS info;
SELECT table_name FROM information_schema.views WHERE table_schema = 'public' AND table_name LIKE 'vw_%' ORDER BY table_name;
