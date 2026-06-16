
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

SELECT COUNT(*) AS nb_lignes_bridge FROM bridge_offre_competence;
