-- Schéma de la base gamesuggestion_db
-- Ordre respecté pour satisfaire les contraintes de clés étrangères

CREATE DATABASE IF NOT EXISTS gamesuggestion_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE gamesuggestion_db;

-- Rôles utilisateurs
CREATE TABLE Roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB;

INSERT INTO Roles (name) VALUES ('user'), ('admin');

-- Utilisateurs (pas d'email, RGPD)
CREATE TABLE Users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_name VARCHAR(50) NOT NULL UNIQUE,
    user_pw_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    role_id INT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES Roles(id)
) ENGINE=InnoDB;

-- Tables de référence (échelles réutilisées)
CREATE TABLE EchellesDE (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB;

INSERT INTO EchellesDE (label) VALUES
    ('Facile'), ('Intermédiaire'), ('Avancé'), ('Difficile'), ('Extrême');

CREATE TABLE EchellesRG (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB;

INSERT INTO EchellesRG (label) VALUES
    ('Aucun'), ('Bas'), ('Moyen'), ('Haut'), ('Extrême');

-- Jeux
CREATE TABLE Games (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_name VARCHAR(150) NOT NULL UNIQUE,
    game_length INT NULL COMMENT 'Durée moyenne du jeu en minutes',
    game_dimension ENUM('2D', '2.5D', '3D') NULL,
    difficulty_id INT NULL,
    execution_id INT NULL,
    randomness_id INT NULL,
    glitchness_id INT NULL,
    FOREIGN KEY (difficulty_id) REFERENCES EchellesDE(id),
    FOREIGN KEY (execution_id) REFERENCES EchellesDE(id),
    FOREIGN KEY (randomness_id) REFERENCES EchellesRG(id),
    FOREIGN KEY (glitchness_id) REFERENCES EchellesRG(id)
) ENGINE=InnoDB;

-- Styles (genres) des jeux, relation N-N
CREATE TABLE Styles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    style_name VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE Style_Games (
    game_id INT NOT NULL,
    style_id INT NOT NULL,
    PRIMARY KEY (game_id, style_id),
    FOREIGN KEY (game_id) REFERENCES Games(id) ON DELETE CASCADE,
    FOREIGN KEY (style_id) REFERENCES Styles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Texte libre par jeu, source de contenu pour le RAG (Chroma)
CREATE TABLE Textes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    source ENUM('steam_blurb', 'steam_reviews') NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (game_id) REFERENCES Games(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Interactions utilisateur <-> jeu (nourrit la SVD)
CREATE TABLE Users_Games (
    user_id INT NOT NULL,
    game_id INT NOT NULL,
    rating TINYINT UNSIGNED NULL,
    source ENUM('onboarding', 'interaction') NOT NULL DEFAULT 'interaction',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_id),
    FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES Games(id) ON DELETE CASCADE,
    CONSTRAINT chk_rating CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
) ENGINE=InnoDB;

-- Préférences déclarées à l'onboarding (0,1 par utilisateur)
CREATE TABLE Preferences (
    user_id INT PRIMARY KEY,
    duration_pref ENUM('court', 'moyen', 'long') NULL,
    dimension_pref ENUM('2D', '2.5D', '3D') NULL,
    difficulty_id INT NULL,
    execution_id INT NULL,
    randomness_id INT NULL,
    glitchness_id INT NULL,
    FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE,
    FOREIGN KEY (difficulty_id) REFERENCES EchellesDE(id),
    FOREIGN KEY (execution_id) REFERENCES EchellesDE(id),
    FOREIGN KEY (randomness_id) REFERENCES EchellesRG(id),
    FOREIGN KEY (glitchness_id) REFERENCES EchellesRG(id)
) ENGINE=InnoDB;

-- Styles préférés (jusqu'à 3, limite gérée en application, pas en base)
CREATE TABLE Preferences_Styles (
    user_id INT NOT NULL,
    style_id INT NOT NULL,
    PRIMARY KEY (user_id, style_id),
    FOREIGN KEY (user_id) REFERENCES Preferences(user_id) ON DELETE CASCADE,
    FOREIGN KEY (style_id) REFERENCES Styles(id) ON DELETE CASCADE
) ENGINE=InnoDB;