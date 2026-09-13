# Compatibility

WORLDLINE has two relevant design histories.

## Research surface

The foundational design proposed general service operations such as world-state reads, subscriptions and transaction execution, with D-Bus/gRPC as possible transports.

## Embedded GWCU surface

The later implementation embedded inside the computer-use/GWCU stack used a Unix socket and six concrete operations:

```text
status
 event
 capture
 arm
 wait
 close
```

That implementation also established the separation between computer-use actuation/window operations and WORLDLINE's facts, predicates, waits, invalidation and receipts.

## Standalone rule

The standalone project preserves the six names as compatibility operations while adding:

- protocol versioning;
- feature discovery;
- general `query` state reads;
- provider and consumer extension points.

Compatibility operations should eventually be backed by the same typed event/predicate machinery as newer APIs rather than maintained as a parallel implementation.
