`timescale 1ns/1ps

module add16_tb();
integer hwb_seed = 1;
initial if (!$value$plusargs("SEED=%d", hwb_seed)) hwb_seed = 1;


    reg [15:0] a;
    reg [15:0] b;
    reg Cin;

    wire [15:0] y;
    wire Co;

    wire [16:0] tb_sum;
    wire tb_co;

    assign tb_sum = a + b;
    assign tb_co = tb_sum[16];

    integer i;
    integer error = 0;

    initial begin
        for (i = 0; i < 100; i = i + 1) begin
            a = {$random(hwb_seed)};
            b = {$random(hwb_seed)};
            Cin = 0;

            #10;
            error = (y !== tb_sum[15:0] || Co !== tb_co) ? error + 1 : error;
        end

        if (error == 0) begin
            $display("HWBENCH_PASS");
        end
        else begin
            $fatal(1, "Test completed with %d / 100 failures===========", error);
        end
    end

    adder_16bit uut (
        .a(a),
        .b(b),
        .Cin(Cin),

        .y(y),
        .Co(Co)
    );

endmodule