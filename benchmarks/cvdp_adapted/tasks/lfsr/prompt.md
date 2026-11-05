Design the RTL for an 8-bit Linear Feedback Shift Register (LFSR) by utilizing the primitive polynomial **x<sup>8</sup>+x<sup>6</sup>+x<sup>5</sup>+x+1** under Galois configuration to construct maximal length pseudo-random sequences.

## Design Specification:

- LFSRs configured in the Galois style operate using an internal feedback system. 
- In this arrangement, the feedback taps directly impact specific bits within the shift register.
- A distinctive characteristic of Galois LFSRs is that only one bit is shifted per clock cycle, with the feedback bit selectively toggling the bits at the designated tap positions.
- In this setup, the output from the final register undergoes an XOR operation with the outputs of selected register bits, which are determined by the coefficients of the primitive polynomial. For a polynomial of degree n, the positions of non-zero coefficients, excluding the nth and zeroth, are considered when performing the XOR operations.

#### Structure of Galois configuration
- Registers: A set of flip-flops connected in series, each holding a single bit
- Feedback mechanism: Feedback is taken from the output of the last flip-flop and applied to various taps (which are bits in the register) using XOR gates
- Shift: On each clock cycle, the bits are shifted to the right, and the feedback bit is XORed with some of the bits in the registers before shifting

#### Working example

Let `lfsr_out [7:0]` be the 8-bit output of LFSR. Assume `lfsr_out[7]` and `lfsr_out[0]` as MSB and LSBs of the output of 8-bit LFSR under Galois configuration with the polynomial **x<sup>8</sup>+x<sup>6</sup>+x <sup>5</sup>+x+1**

Expanding the coefficients of the polynomial,

**1 . x<sup>8</sup> + 0 . x<sup>7</sup> + 1 . x<sup>6</sup> + 1 . x<sup>5</sup> + 0 . x<sup>4</sup> + 0 . x<sup>3</sup> + 0 . x<sup>2</sup> + 1 . x<sup>1</sup> + 1 . x<sup>0</sup>**

In this n-degree polynomial, 'n' represents the number of registers and the presence of non-zero coefficients in terms except the n-th term and zeroth term represent the tap positions in the 8-bit LFSR based on Galois configuration. The tap positions define the XOR operation with the final register value. As per the above primitive polynomial, 8 registers are needed to construct the LFSR with 3 XOR operations.

Here, 
`1 . x^6` represents the XOR operation between `lfsr_out[6]` XOR `lfsr_out[0]`\
 `1 . x^5` represents the XOR operation between `lfsr_out[5]` XOR `lfsr_out[0]`\
 `1 . x^1` represents the XOR operation between `lfsr_out[1]` XOR `lfsr_out[0]`\

 The LFSR shifts the bits in the following way during every clock cycle. 

lfsr_out[7] = lfsr_out[0]\
lfsr_out[6] = lfsr_out[7]\
lfsr_out[5] = lfsr_out[6] XOR lfsr_out[0]\
lfsr_out[4] = lfsr_out[5] XOR lfsr_out[0]\
lfsr_out[3] = lfsr_out[4]\
lfsr_out[2] = lfsr_out[3]\
lfsr_out[1] = lfsr_out[2]\
lfsr_out[0] = lfsr_out[1] XOR lfsr_out[0]

When the reset is HIGH with the LFSR seed as 8'b10011001 , the `lfsr_out` for a few clock cycles will be as follows:

clk #1 -> lfsr_out = 8'b11111101\
clk #2 -> lfsr_out = 8'b11001111\
clk #3 -> lfsr_out = 8'b11010110\
clk #4 -> lfsr_out = 8'b01101011\
clk #5 -> lfsr_out = 8'b10000100

#### Functional requirements:
- The constructed 8-bit LFSR based on Galois configuration has to generate a maximal length sequence of (2<sup>8</sup> - 1) pseudo-random 8-bit sequences without supporting all-zero seed. In this case, the pseudo-random sequences fall in the range of values between 0000_0001 and 1111_1111

- Following should be the interface of the RTL design of 8-bit LFSR module named `lfsr_8bit`

#### Inputs:
- `clock (1-bit)`: A single-bit input clock essential for the operation of the 8-bit LFSR, controlling data movement on the positive clock edge. Normally, the clock operates with a 50:50 duty cycle.
- `reset (1-bit)`: A control signal that asynchronously resets the LFSR output to the initial seed when active LOW.
- `lfsr_seed (8-bit, array index [7:0])`: An 8-bit initial seed that initializes the LFSR to trigger the pseudo-random sequence generation upon an asynchronous active LOW reset.

#### Output:
- `lfsr_out (8-bit, array index [7:0])`: Represents the output from the 8-bit LFSR. A new random value is output at each positive clock edge when the value of `reset` is HIGH.

Source: NVIDIA CVDP v1.1.0 example cvdp_copilot_lfsr_0001.
Adaptation: native iverilog checker, not official CVDP scoring. Zero seed is outside this task's contract.
