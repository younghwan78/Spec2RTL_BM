# timer_irq

Implement `timer_irq`. `rst` is synchronous, active-high and clears all state. `prescale`, `compare` and `oneshot` only change while `rst` is high; behaviour otherwise is undefined.

- While `enable` is high and the timer is not stopped, a prescaler counts every clock. When it equals `prescale` a tick occurs in that cycle and the prescaler returns to 0 on the rising edge; otherwise it increments. So a tick occurs every `prescale + 1` enabled cycles.
- `enable` low holds the prescaler and `count` unchanged and clears the stopped condition on that rising edge.
- On a tick, if `count == compare`, the event fires: `count` returns to 0 and `irq` is set. If `oneshot` is high the timer then stops: no prescaler or count updates occur until `enable` has been low for at least one rising edge. On a tick with `count != compare`, `count` increments.
- `irq` is sticky. `irq_clear` high on a rising edge clears it, unless an event fires on the same edge, in which case `irq` is set.
- `count` and `irq` are registered and show state after the most recent rising edge.

Interface:

```systemverilog
module timer_irq (
  input clk, input rst,
  input enable, input oneshot,
  input [7:0] prescale, input [15:0] compare,
  input irq_clear,
  output [15:0] count, output irq
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
