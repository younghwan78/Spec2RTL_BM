module timer_irq (
  input clk, input rst,
  input enable, input oneshot,
  input [7:0] prescale, input [15:0] compare,
  input irq_clear,
  output [15:0] count, output irq
);
  reg [7:0] pre;
  reg [15:0] cnt;
  reg irq_q, done;
  wire tick = enable && !done && pre == prescale;
  wire hit = tick && cnt == compare;
  assign count = cnt;
  assign irq = irq_q;
  always @(posedge clk)
    if (rst) begin pre <= 0; cnt <= 0; irq_q <= 0; done <= 0; end
    else begin
      if (enable && !done) pre <= tick ? 8'b0 : pre + 8'd1;
      if (!enable) done <= 0;
      if (tick) begin
        if (hit) begin cnt <= 0; if (oneshot) done <= 1; end
        else cnt <= cnt + 16'd1;
      end
      if (hit) irq_q <= 1;
      else if (irq_clear) irq_q <= 0;
    end
endmodule
