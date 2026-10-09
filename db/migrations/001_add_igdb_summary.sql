-- Ajoute 'igdb_summary' aux sources possibles de la table Textes
-- (résumé IGDB pour les jeux qui ne sont pas sur Steam).
-- À lancer une fois sur une base existante :
--   docker exec -i gamesuggestion-mysql mysql -uroot -p gamesuggestion_db < db/migrations/001_add_igdb_summary.sql
ALTER TABLE Textes
    MODIFY source ENUM('steam_blurb', 'steam_reviews', 'igdb_summary') NOT NULL;