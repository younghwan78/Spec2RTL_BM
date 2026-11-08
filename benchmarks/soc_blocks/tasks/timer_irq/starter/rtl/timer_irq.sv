module timer_irq (
  input clk, input rst,
  input enable, input oneshot,
  input [7:0] prescale, input [15:0] compare,
  input irq_clear,
  output [15:0] count, output irq
);
  // Implement the specified behaviour here.
endmodule
