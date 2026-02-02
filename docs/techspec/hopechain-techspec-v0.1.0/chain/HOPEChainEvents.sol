// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title HOPEChainEvents - Minimal event interface for HOPE Chain settlement/audit
/// @notice Store hashes + signatures on-chain; keep raw prompts/outputs off-chain (hash/pointer only).
contract HOPEChainEvents {
    event TaskCreated(bytes32 indexed taskId, string clientDid, bytes32 taskHash, uint256 budgetUnits);
    event TaskAssigned(bytes32 indexed taskId, string workerDid, string[] verifierDids);

    event ResultSubmitted(bytes32 indexed taskId, string workerDid, bytes32 resultHash, bytes workerSig);
    event Verified(bytes32 indexed taskId, string verifierDid, uint16 scoreBps, uint8 verdict, bytes verifierSig);

    event Settled(bytes32 indexed taskId, uint256 paidWorkerUnits, uint256 paidVerifierUnits, uint256 treasuryUnits);

    event Slashed(string nodeDid, uint256 amountUnits, uint16 reasonCode);
    event ReputationUpdated(string nodeDid, uint16 newRepBps);

    event PolicyUpdated(bytes32 indexed policyId, string version, bytes32 paramsHash);

    event DisputeOpened(bytes32 indexed taskId, string openerDid, uint16 reasonCode);
    event DisputeResolved(bytes32 indexed taskId, uint8 outcome, bytes32 adjustmentsHash);

    // verdict: 0=accepted, 1=rejected, 2=retry
    // scoreBps: 0..10000
}
