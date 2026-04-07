// Magic byte signatures for allowed file types.
// We check the actual bytes, not just the Content-Type header or file extension,
// because both can be spoofed trivially by a malicious user.
const ALLOWED_SIGNATURES: Array<{ mimeType: string; bytes: number[]; offset: number }> = [
  { mimeType: 'application/pdf', bytes: [0x25, 0x50, 0x44, 0x46], offset: 0 }, // %PDF
  { mimeType: 'image/jpeg',      bytes: [0xff, 0xd8, 0xff],         offset: 0 }, // JPEG
  { mimeType: 'image/png',       bytes: [0x89, 0x50, 0x4e, 0x47],   offset: 0 }, // PNG
];

const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20MB — enforced in DB too

export type FileValidationResult =
  | { valid: true; mimeType: string }
  | { valid: false; error: string };

export async function validateUploadedFile(file: File): Promise<FileValidationResult> {
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return { valid: false, error: `File exceeds 20MB limit (received ${(file.size / 1024 / 1024).toFixed(1)}MB)` };
  }

  // Read the first 8 bytes to check magic bytes
  const header = await file.slice(0, 8).arrayBuffer();
  const bytes = new Uint8Array(header);

  const match = ALLOWED_SIGNATURES.find(({ bytes: sig, offset }) =>
    sig.every((byte, index) => bytes[offset + index] === byte)
  );

  if (!match) {
    return {
      valid: false,
      error: 'Invalid file type. Please upload a PDF, JPEG, or PNG.',
    };
  }

  return { valid: true, mimeType: match.mimeType };
}
