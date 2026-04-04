# PLAN.md (TASK-0038)

Phase C: Vehicle CRUD + Lifecycle.

## Strategy

1. **Service Layer**: Implement `vehicle_service.py` functions for create/update.
2. **Lifecycle Transitions**: Implement state machine guards for active/inactive/deleted.
3. **Endpoints**: Register FastAPI routers.
4. **Idempotency**: Integrate with outbox for idempotent creation.
5. **Soft Delete**: Implement logical deletion with timestamping.

## Verification

Postman/Curl tests of all vehicle endpoints.
