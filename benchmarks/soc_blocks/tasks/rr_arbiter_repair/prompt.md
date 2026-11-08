# rr_arbiter

Implement `rr_arbiter`, a combinational-grant round-robin arbiter with a lock. N >= 2. `rst` is synchronous and active-high; it sets the priority pointer to requester 0 and clears any lock.

- `grant` is one-hot or zero. It depends combinationally on `req` and on registered state.
- If a lock is held and the locked owner still requests, `grant` selects the owner regardless of the pointer.
- Otherwise, `grant` selects the first requester at or after the pointer, in increasing index with wrap-around. With no requests, `grant` is zero.
- State changes only on rising edges. When `accept` is high and `grant` is nonzero: if `lock` is high, the granted requester becomes (or stays) the locked owner and the pointer is unchanged; if `lock` is low, any lock is released and the pointer moves to the requester after the granted one, modulo N.
- When `accept` is low or `grant` is zero, the pointer does not move. A lock whose owner no longer requests is released at that edge unless a new accepted grant applies.

Interface:

```systemverilog
module rr_arbiter #(parameter N = 4) (
  input clk, input rst,
  input [N-1:0] req, input lock, input accept,
  output [N-1:0] grant
);
```

The RTL file in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name, parameters and ports, and do not rewrite unrelated logic.


Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
