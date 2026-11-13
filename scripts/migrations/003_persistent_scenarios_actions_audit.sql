-- Phase 4 persistence. This migration adds only Twin-owned objects.
-- Legacy dbo and FDE_VIEWS objects are not modified.

IF OBJECT_ID(N'Twin.Scenarios', N'U') IS NULL
CREATE TABLE Twin.Scenarios (
    scenario_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
    baseline_version BIGINT NOT NULL,
    scenario_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    seed INT NULL,
    parameters NVARCHAR(MAX) NOT NULL,
    created_at DATETIME2(3) NOT NULL,
    approved_at DATETIME2(3) NULL,
    CONSTRAINT CK_Twin_Scenarios_Parameters CHECK (ISJSON(parameters) = 1)
);
GO

IF OBJECT_ID(N'Twin.Actions', N'U') IS NULL
CREATE TABLE Twin.Actions (
    action_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
    scenario_id UNIQUEIDENTIFIER NOT NULL,
    vehicle_id VARCHAR(40) NOT NULL,
    shipment_id VARCHAR(40) NOT NULL,
    warehouse_id VARCHAR(40) NOT NULL,
    recommendation NVARCHAR(MAX) NOT NULL,
    estimated_cost DECIMAL(18,2) NULL,
    carbon_delta_kg DECIMAL(18,3) NULL,
    status VARCHAR(30) NOT NULL,
    proposed_at DATETIME2(3) NOT NULL,
    approved_at DATETIME2(3) NULL,
    executed_at DATETIME2(3) NULL,
    CONSTRAINT FK_Twin_Actions_Scenario
        FOREIGN KEY (scenario_id) REFERENCES Twin.Scenarios(scenario_id),
    CONSTRAINT FK_Twin_Actions_Vehicle
        FOREIGN KEY (vehicle_id) REFERENCES Twin.Vehicles(vehicle_id),
    CONSTRAINT FK_Twin_Actions_Shipment
        FOREIGN KEY (shipment_id) REFERENCES Twin.Shipments(shipment_id),
    CONSTRAINT FK_Twin_Actions_Warehouse
        FOREIGN KEY (warehouse_id) REFERENCES Twin.Warehouses(warehouse_id)
);
GO

IF OBJECT_ID(N'Twin.Audit', N'U') IS NULL
CREATE TABLE Twin.Audit (
    audit_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    correlation_id UNIQUEIDENTIFIER NOT NULL,
    scenario_id UNIQUEIDENTIFIER NULL,
    session_id VARCHAR(100) NULL,
    node_name VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100) NULL,
    status VARCHAR(30) NOT NULL,
    input_summary NVARCHAR(MAX) NULL,
    output_summary NVARCHAR(MAX) NULL,
    evidence NVARCHAR(MAX) NULL,
    approval_status VARCHAR(30) NULL,
    error_code VARCHAR(80) NULL,
    recorded_at DATETIME2(3) NOT NULL
        CONSTRAINT DF_Twin_Audit_RecordedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Twin_Audit_Scenario
        FOREIGN KEY (scenario_id) REFERENCES Twin.Scenarios(scenario_id)
);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_Twin_Actions_Scenario_Status'
      AND object_id = OBJECT_ID(N'Twin.Actions')
)
    CREATE INDEX IX_Twin_Actions_Scenario_Status
        ON Twin.Actions(scenario_id, status);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_Twin_Audit_Correlation'
      AND object_id = OBJECT_ID(N'Twin.Audit')
)
    CREATE INDEX IX_Twin_Audit_Correlation
        ON Twin.Audit(correlation_id, recorded_at DESC);
GO

GRANT SELECT ON OBJECT::Twin.Scenarios TO USR_FDE_RO;
GRANT SELECT ON OBJECT::Twin.Actions TO USR_FDE_RO;
GRANT SELECT ON OBJECT::Twin.Audit TO USR_FDE_RO;
GO
