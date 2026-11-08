# axis_downsizer

Implement `axis_downsizer`, which converts a 32-bit stream to an 8-bit stream. `rst` is synchronous, active-high and discards any held beat.

- `s_keep` is always one of 4'b0001, 4'b0011, 4'b0111, 4'b1111 when `s_valid` is high; other values need not be handled. Only kept bytes are emitted, least-significant byte first.
- The block holds one input beat at a time. Let `left` be the bytes of the held beat not yet transferred on the master side.
- `m_valid` is high exactly when `left != 0`. `m_data` is the next byte. `m_last` is high exactly on the final byte of a held beat whose `s_last` was high.
- `s_ready` is high exactly when `left == 0`, or when `left == 1 && m_ready` (the final byte transfers in this cycle), so that consecutive beats have no bubble. `s_ready` may depend combinationally on `m_ready`.
- A master-side transfer occurs on a rising edge when `m_valid && m_ready`. A slave-side transfer occurs when `s_valid && s_ready`; the first byte of that beat is visible in the next cycle.
- While `m_valid` is high and `m_ready` is low, `m_data` and `m_last` hold. They are undefined when `m_valid` is low.

Interface:

```systemverilog
module axis_downsizer (
  input clk, input rst,
  input s_valid, output s_ready, input [31:0] s_data, input [3:0] s_keep, input s_last,
  output m_valid, input m_ready, output [7:0] m_data, output m_last
);
```

The RTL file in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name, parameters and ports, and do not rewrite unrelated logic.


Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
