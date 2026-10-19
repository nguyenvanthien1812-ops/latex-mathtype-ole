r"""
cli.py -- Chuyen doi tu dong lenh (khong can GUI).

Vi du:
  python cli.py baigiang.docx out.docx
  python cli.py in.docx out.docx --ref mau_mathtype.docx   # NEN DUNG

--ref: mot file Word chua MOT cong thuc ban tu go bang MathType (hoac mot
oleObject .bin). Chuong trinh se sao y CLSID + CompObj + header tu do, nho vay
Word route dung sang MathType thay vi bao "Equation Editor 3.0".
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from docx_convert import convert_docx, reference_template


def main(argv=None):
    ap = argparse.ArgumentParser(description="LaTeX ($...$) -> MathType OLE trong Word")
    ap.add_argument("input", help="file .docx dau vao")
    ap.add_argument("output", help="file .docx dau ra")
    ap.add_argument("--ref", metavar="FILE",
                    help="file MathType mau (.docx co 1 cong thuc MathType, hoac .bin) "
                         "de sao vo OLE that -> MathType mo duoc")
    args = ap.parse_args(argv)

    template = None
    if args.ref:
        template = reference_template(args.ref)
        print(f"Da nap vo OLE tu {args.ref}")
        print(f"  CLSID  : {template.get('clsid_str')}")
        print(f"  CompObj: {'co' if template.get('compobj') else 'khong'} | "
              f"\\x01Ole: {'co' if template.get('ole') else 'khong'} | "
              f"header: {'co' if template.get('equation_native') else 'khong'}")

    stats = convert_docx(args.input, args.output, log=print, template=template)
    print(f"Xong: chuyen {stats['converted']} cong thuc, bo qua {stats['failed']}.")
    print(f"File ra: {args.output}")
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
