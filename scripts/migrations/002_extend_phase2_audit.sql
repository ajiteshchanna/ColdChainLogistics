-- Phase 2 audit metadata. Existing audit rows remain intact.

IF COL_LENGTH(N'FDE_VIEWS.AgentAuditLog', N'CorrelationID') IS NULL
    ALTER TABLE FDE_VIEWS.AgentAuditLog
        ADD CorrelationID UNIQUEIDENTIFIER NULL;
GO

IF COL_LENGTH(N'FDE_VIEWS.AgentAuditLog', N'Status') IS NULL
    ALTER TABLE FDE_VIEWS.AgentAuditLog
        ADD Status VARCHAR(30) NULL;
GO

IF COL_LENGTH(N'FDE_VIEWS.AgentAuditLog', N'ApprovalStatus') IS NULL
    ALTER TABLE FDE_VIEWS.AgentAuditLog
        ADD ApprovalStatus VARCHAR(30) NULL;
GO

IF COL_LENGTH(N'FDE_VIEWS.AgentAuditLog', N'ErrorCode') IS NULL
    ALTER TABLE FDE_VIEWS.AgentAuditLog
        ADD ErrorCode VARCHAR(80) NULL;
GO
