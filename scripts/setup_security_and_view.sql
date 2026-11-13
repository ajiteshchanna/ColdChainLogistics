-- FDE semantic layer and least-privilege setup.
-- Run with SQLCMD variable FDE_AGENT_PASSWORD supplied by a secret store.
-- Example: sqlcmd -v FDE_AGENT_PASSWORD="..." -i setup_security_and_view.sql

IF SCHEMA_ID(N'FDE_VIEWS') IS NULL
    EXEC(N'CREATE SCHEMA FDE_VIEWS');
GO

CREATE OR ALTER VIEW FDE_VIEWS.VW_ACTIVE_FLEET
AS
SELECT
    TS_UTC AS [Timestamp],
    V_LAT AS [Latitude],
    V_LON AS [Longitude],
    CAST(IOT_TEMP_VAL_C AS FLOAT) AS [Current_Temperature_C],
    CGO_COND_CD AS [Cargo_Condition_Code],
    RISK_CLS_TXT AS [Risk_Classification],
    DELAY_PROB_DEC AS [Delay_Probability],
    PRT_CNG_LVL AS [Port_Congestion_Level],
    RT_RSK_IDX AS [Route_Risk_Index]
FROM dbo.TBL_SC_FLEET_HIST_RAW;
GO

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'USR_FDE_RO')
BEGIN
    CREATE LOGIN USR_FDE_RO
        WITH PASSWORD = '$(FDE_AGENT_PASSWORD)';
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'USR_FDE_RO')
    CREATE USER USR_FDE_RO FOR LOGIN USR_FDE_RO;
GO

IF OBJECT_ID(N'FDE_VIEWS.AgentAuditLog', N'U') IS NULL
BEGIN
    CREATE TABLE FDE_VIEWS.AgentAuditLog (
        LogID BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        [Timestamp] DATETIME2(3) NOT NULL
            CONSTRAINT DF_AgentAuditLog_Timestamp DEFAULT SYSUTCDATETIME(),
        SessionID VARCHAR(100) NOT NULL,
        NodeExecuted VARCHAR(100) NOT NULL,
        ToolName VARCHAR(100) NOT NULL,
        Content NVARCHAR(MAX) NOT NULL,
        CorrelationID UNIQUEIDENTIFIER NULL,
        Status VARCHAR(30) NULL,
        ApprovalStatus VARCHAR(30) NULL,
        ErrorCode VARCHAR(80) NULL
    );
END;
GO

GRANT SELECT ON OBJECT::FDE_VIEWS.VW_ACTIVE_FLEET TO USR_FDE_RO;
GRANT INSERT ON OBJECT::FDE_VIEWS.AgentAuditLog TO USR_FDE_RO;
DENY SELECT ON OBJECT::dbo.TBL_SC_FLEET_HIST_RAW TO USR_FDE_RO;
DENY INSERT, UPDATE, DELETE, ALTER ON SCHEMA::dbo TO USR_FDE_RO;
GO
