# crc32_byte

Implement `crc32_byte`, computing CRC-32 (IEEE 802.3: reflected, polynomial 0x04C11DB7 / reflected form 0xEDB88320, initial value 0xFFFFFFFF, final XOR 0xFFFFFFFF) one byte per enabled clock.

- `rst` (synchronous, active-high) and `init` both load the initial value on a rising edge. `rst` and `init` have priority over `en`.
- When `en` is high and neither `rst` nor `init` is high, the byte `data` is absorbed on the rising edge, least-significant bit first. When `en` is low, the state holds.
- `crc` is the bitwise inverse of the internal state, with no extra latency. For example, after init and the ASCII bytes "123456789", `crc` is 0xCBF43926; directly after init, `crc` is 0.

Interface:

```systemverilog
module crc32_byte (
  input clk, input rst,
  input init, input en, input [7:0] data,
  output [31:0] crc
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
