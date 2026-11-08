module secded_codec (
  input [7:0] enc_data, output [12:0] enc_cw,
  input [12:0] dec_cw, output [7:0] dec_data, output sec, output ded
);
  wire [3:0] c = {enc_data[4]^enc_data[5]^enc_data[6]^enc_data[7],
                  enc_data[1]^enc_data[2]^enc_data[3]^enc_data[7],
                  enc_data[0]^enc_data[2]^enc_data[3]^enc_data[5]^enc_data[6],
                  enc_data[0]^enc_data[1]^enc_data[3]^enc_data[4]^enc_data[6]};
  assign enc_cw = {^{enc_data, c}, c, enc_data};
  wire [3:0] s = {dec_cw[11]^dec_cw[4]^dec_cw[5]^dec_cw[6]^dec_cw[7],
                  dec_cw[10]^dec_cw[1]^dec_cw[2]^dec_cw[3]^dec_cw[7],
                  dec_cw[9]^dec_cw[0]^dec_cw[2]^dec_cw[3]^dec_cw[5]^dec_cw[6],
                  dec_cw[8]^dec_cw[0]^dec_cw[1]^dec_cw[3]^dec_cw[4]^dec_cw[6]};
  wire pe = ^dec_cw;
  assign sec = pe && s <= 12;
  assign ded = (!pe && s != 0) || (pe && s > 12);
  wire [7:0] flip = !sec ? 8'b0 :
                    s == 3 ? 8'h01 : s == 5 ? 8'h02 : s == 6 ? 8'h04 : s == 7 ? 8'h08 :
                    s == 9 ? 8'h10 : s == 10 ? 8'h20 : s == 11 ? 8'h40 : s == 12 ? 8'h80 : 8'b0;
  assign dec_data = dec_cw[7:0] ^ flip;
endmodule
