-- Smart Food Rescue — MySQL schema (AWS RDS, MySQL 8.x)
-- Run once:  mysql -h <rds-endpoint> -u admin -p smart_food_rescue < schema.sql
-- (create the database first:  CREATE DATABASE smart_food_rescue CHARACTER SET utf8mb4;)
-- (Or simply run `flask --app run init-db` with DATABASE_URL pointing at RDS.)


-- ---------------------------------------------------------------
-- Users: donors, NGOs and admins share one table, split by role
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    name                  VARCHAR(100)  NOT NULL,
    email                 VARCHAR(120)  NOT NULL UNIQUE,
    password_hash         VARCHAR(255)  NOT NULL,           -- Werkzeug hash, never plain text
    role                  ENUM('donor','ngo','admin') NOT NULL,
    organization          VARCHAR(150),                     -- mess / restaurant / NGO name
    phone                 VARCHAR(20),
    verification_doc_key  VARCHAR(255),                     -- S3 key of NGO registration doc
    is_verified           BOOLEAN NOT NULL DEFAULT FALSE,   -- admin verifies NGOs
    active                BOOLEAN NOT NULL DEFAULT TRUE,    -- admin can deactivate
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_role (role)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Food listings posted by donors
-- Lifecycle: available -> requested -> approved -> picked_up -> completed
--            (available/requested listings past available_until -> expired, set by the AWS Lambda job)
-- Already created the table without 'expired'? Run:
--   ALTER TABLE food_listings MODIFY status ENUM('available','requested','approved','picked_up','completed','expired')
--     NOT NULL DEFAULT 'available';
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS food_listings (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    donor_id         INT          NOT NULL,
    food_name        VARCHAR(120) NOT NULL,
    food_type        ENUM('veg','non-veg','mixed') NOT NULL DEFAULT 'veg',
    quantity         INT          NOT NULL,                 -- approx. number of meals/servings
    location         VARCHAR(255) NOT NULL,
    description      TEXT,
    image_key        VARCHAR(255),                          -- S3 object key, e.g. food/ab12.jpg
    available_until  DATETIME     NOT NULL,
    status           ENUM('available','requested','approved','picked_up','completed','expired')
                     NOT NULL DEFAULT 'available',
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_listing_donor FOREIGN KEY (donor_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_quantity CHECK (quantity > 0),
    INDEX idx_listing_status (status),
    INDEX idx_listing_location (location)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Pickup requests from NGOs
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pickup_requests (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    food_id     INT NOT NULL,
    ngo_id      INT NOT NULL,
    message     VARCHAR(500),
    status      ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_req_food FOREIGN KEY (food_id) REFERENCES food_listings(id) ON DELETE CASCADE,
    CONSTRAINT fk_req_ngo  FOREIGN KEY (ngo_id)  REFERENCES users(id)         ON DELETE CASCADE,
    CONSTRAINT uq_one_request_per_ngo UNIQUE (food_id, ngo_id),
    INDEX idx_req_status (status)
) ENGINE=InnoDB;

-- Useful report query for the analytics dashboard:
-- SELECT COUNT(*) AS total_listings,
--        SUM(status='completed') AS completed_pickups,
--        COALESCE(SUM(CASE WHEN status='completed' THEN quantity END),0) AS meals_donated
-- FROM food_listings;
