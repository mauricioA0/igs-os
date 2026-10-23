export { ApprovalGateProvider, withApprovalGate, type ApprovalRef, type GatedProps, type ProposeFn, type ProposedAction } from "./with-approval-gate";
export { ErrorBoundary, withErrorBoundary, type ErrorFallbackProps } from "./with-error-boundary";
export { FeatureFlagsProvider, useFlag, withFeatureFlag, type Flags } from "./with-feature-flag";
export { withPermission } from "./with-permission";
export { TrackingProvider, useTrack, withTracking, type TrackFn } from "./with-tracking";
export {
  capabilityFor,
  PrincipalProvider,
  useCapability,
  usePrincipal,
  type Capability,
  type Principal,
  type Role,
  type ToolClass,
} from "./permissions";
