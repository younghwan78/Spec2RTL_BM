# secded_codec

Implement `secded_codec`, a purely combinational Hamming SEC-DED codec for 8 data bits and 5 check bits.

Encoding: `enc_cw = {p, c[3:0], enc_data[7:0]}` where, writing d for `enc_data`,
c0 = d0^d1^d3^d4^d6, c1 = d0^d2^d3^d5^d6, c2 = d1^d2^d3^d7, c3 = d4^d5^d6^d7, and p is the XOR of all d and c bits.

Decoding of `dec_cw = {p, c[3:0], d[7:0]}`: compute syndrome s[3:0] where s0 = c0^d0^d1^d3^d4^d6, s1 = c1^d0^d2^d3^d5^d6, s2 = c2^d1^d2^d3^d7, s3 = c3^d4^d5^d6^d7, and pe = XOR of all 13 bits.

- pe=0, s=0: no error. `sec`=0, `ded`=0, `dec_data`=d.
- pe=1, s<=12: single-bit error. `sec`=1, `ded`=0. `dec_data` is d with the bit named by s corrected: s=3,5,6,7,9,10,11,12 correct d0,d1,d2,d3,d4,d5,d6,d7 respectively; any other s (0,1,2,4,8) means a check bit was hit and d is unchanged.
- Otherwise (pe=0 with s!=0, or pe=1 with s>12): uncorrectable. `sec`=0, `ded`=1, `dec_data`=d unchanged.

Interface:

```systemverilog
module secded_codec (
  input [7:0] enc_data, output [12:0] enc_cw,
  input [12:0] dec_cw, output [7:0] dec_data, output sec, output ded
);
```

Submit synthesizable SystemVerilog only. Keep the exact module name, parameters and ports. No testbench or simulation system tasks belong in the submitted RTL; `$clog2` is allowed.
