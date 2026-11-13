-- Phase 1 digital-twin schema. Legacy dbo tables are not modified.

IF SCHEMA_ID(N'Twin') IS NULL
    EXEC(N'CREATE SCHEMA Twin');
GO

IF OBJECT_ID(N'Twin.Vehicles', N'U') IS NULL
CREATE TABLE Twin.Vehicles (
    vehicle_id VARCHAR(40) NOT NULL PRIMARY KEY,
    registration VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    speed_kph DECIMAL(8,2) NULL,
    route_id VARCHAR(40) NOT NULL,
    waypoint_index INT NOT NULL,
    compressor_state VARCHAR(30) NOT NULL,
    compressor_health DECIMAL(5,4) NOT NULL,
    fuel_level_percent DECIMAL(5,2) NULL,
    state_version BIGINT NOT NULL DEFAULT 0,
    updated_at DATETIME2(3) NOT NULL
);
GO

IF OBJECT_ID(N'Twin.Shipments', N'U') IS NULL
CREATE TABLE Twin.Shipments (
    shipment_id VARCHAR(40) NOT NULL PRIMARY KEY,
    vehicle_id VARCHAR(40) NOT NULL,
    cargo_category VARCHAR(60) NOT NULL,
    min_temp_c DECIMAL(6,2) NOT NULL,
    max_temp_c DECIMAL(6,2) NOT NULL,
    origin_name VARCHAR(160) NOT NULL,
    destination_name VARCHAR(160) NOT NULL,
    cargo_value DECIMAL(18,2) NOT NULL,
    quantity DECIMAL(18,3) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'in_transit',
    CONSTRAINT FK_Twin_Shipments_Vehicle
        FOREIGN KEY (vehicle_id) REFERENCES Twin.Vehicles(vehicle_id)
);
GO

IF OBJECT_ID(N'Twin.Warehouses', N'U') IS NULL
CREATE TABLE Twin.Warehouses (
    warehouse_id VARCHAR(40) NOT NULL PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    total_capacity DECIMAL(18,3) NOT NULL,
    available_capacity DECIMAL(18,3) NOT NULL,
    min_temp_c DECIMAL(6,2) NOT NULL,
    max_temp_c DECIMAL(6,2) NOT NULL,
    available BIT NOT NULL DEFAULT 1
);
GO

IF OBJECT_ID(N'Twin.Routes', N'U') IS NULL
CREATE TABLE Twin.Routes (
    route_id VARCHAR(40) NOT NULL PRIMARY KEY,
    origin_name VARCHAR(160) NOT NULL,
    destination_name VARCHAR(160) NOT NULL,
    geometry_json NVARCHAR(MAX) NOT NULL,
    source VARCHAR(40) NOT NULL,
    CONSTRAINT CK_Twin_Routes_Geometry CHECK (ISJSON(geometry_json) = 1)
);
GO

IF OBJECT_ID(N'Twin.Events', N'U') IS NULL
CREATE TABLE Twin.Events (
    event_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
    aggregate_type VARCHAR(40) NOT NULL,
    aggregate_id VARCHAR(80) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    occurred_at DATETIME2(3) NOT NULL,
    source VARCHAR(40) NOT NULL,
    scenario_id UNIQUEIDENTIFIER NULL,
    correlation_id UNIQUEIDENTIFIER NOT NULL,
    payload NVARCHAR(MAX) NOT NULL,
    CONSTRAINT CK_Twin_Events_Payload CHECK (ISJSON(payload) = 1)
);
GO

IF OBJECT_ID(N'Twin.Telemetry', N'U') IS NULL
CREATE TABLE Twin.Telemetry (
    telemetry_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    event_id UNIQUEIDENTIFIER NOT NULL UNIQUE,
    vehicle_id VARCHAR(40) NOT NULL,
    shipment_id VARCHAR(40) NOT NULL,
    observed_at DATETIME2(3) NOT NULL,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    internal_temperature_c DECIMAL(7,3) NOT NULL,
    ambient_temperature_c DECIMAL(7,3) NOT NULL,
    humidity_percent DECIMAL(6,3) NOT NULL,
    compressor_state VARCHAR(30) NOT NULL,
    compressor_health DECIMAL(5,4) NOT NULL,
    fuel_level_percent DECIMAL(5,2) NULL,
    quality VARCHAR(20) NOT NULL,
    source VARCHAR(40) NOT NULL,
    scenario_id UNIQUEIDENTIFIER NULL,
    CONSTRAINT FK_Twin_Telemetry_Vehicle
        FOREIGN KEY (vehicle_id) REFERENCES Twin.Vehicles(vehicle_id),
    CONSTRAINT FK_Twin_Telemetry_Shipment
        FOREIGN KEY (shipment_id) REFERENCES Twin.Shipments(shipment_id)
);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_Twin_Telemetry_Vehicle_Time'
      AND object_id = OBJECT_ID(N'Twin.Telemetry')
)
    CREATE INDEX IX_Twin_Telemetry_Vehicle_Time
        ON Twin.Telemetry(vehicle_id, observed_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_Twin_Events_Aggregate_Time'
      AND object_id = OBJECT_ID(N'Twin.Events')
)
    CREATE INDEX IX_Twin_Events_Aggregate_Time
        ON Twin.Events(aggregate_type, aggregate_id, occurred_at);
GO

CREATE OR ALTER VIEW FDE_VIEWS.VW_TWIN_ACTIVE_FLEET
AS
SELECT
    vehicle_id AS Vehicle_ID,
    registration AS Registration,
    status AS Status,
    latitude AS Latitude,
    longitude AS Longitude,
    speed_kph AS Speed_KPH,
    route_id AS Route_ID,
    compressor_state AS Compressor_State,
    compressor_health AS Compressor_Health,
    fuel_level_percent AS Fuel_Level_Percent,
    updated_at AS Updated_At,
    state_version AS State_Version
FROM Twin.Vehicles;
GO

GRANT SELECT ON OBJECT::FDE_VIEWS.VW_TWIN_ACTIVE_FLEET TO USR_FDE_RO;
GO
