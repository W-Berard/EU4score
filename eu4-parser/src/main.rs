//! Convertit une sauvegarde texte d'Europa Universalis IV en JSON avec jomini.
//!
//! Usage : eu4-parser <sauvegarde.eu4> <sortie.json>
//!
//! Codes de sortie : 0 succès, 1 erreur de traitement, 2 mauvais arguments.

use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::process::ExitCode;

use jomini::TextTape;
use jomini::json::{DuplicateKeyMode, JsonOptions, TypeNarrowing};

/// En-tête des sauvegardes texte, que jomini ne sait pas lire.
const TEXT_HEADER: &[u8] = b"EU4txt";
/// En-tête des sauvegardes binary (ironman).
const BINARY_HEADER: &[u8] = b"EU4bin";
/// Signature d'une archive zip (sauvegarde compressée).
const ZIP_MAGIC: &[u8] = b"PK\x03\x04";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    let [_, input, output] = args.as_slice() else {
        eprintln!("usage : eu4-parser <sauvegarde.eu4> <sortie.json>");
        return ExitCode::from(2);
    };

    match convert(input, output) {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("erreur : {message}");
            ExitCode::FAILURE
        }
    }
}

/// Lit la sauvegarde `input` et écrit son contenu en JSON dans `output`.
fn convert(input: &str, output: &str) -> Result<(), String> {
    let data = fs::read(input).map_err(|e| format!("lecture de {input} impossible : {e}"))?;
    let text = gamestate_text(&data)?;
    let tape = TextTape::from_slice(text).map_err(|e| format!("sauvegarde illisible : {e}"))?;

    // Group : les clés répétées (active_war par ex.) deviennent une liste, sinon le module json de Python ne garde que la dernière.
    // Unquoted : seules les valeurs sans guillemets sont converties en nombre ou booléen pour qu'un nom de joueur avec des chiffres reste un string.
    let options = JsonOptions::new()
        .with_duplicate_keys(DuplicateKeyMode::Group)
        .with_type_narrowing(TypeNarrowing::Unquoted);

    let file = File::create(output).map_err(|e| format!("création de {output} impossible : {e}"))?;
    let mut writer = BufWriter::new(file);

    // Le JSON est écrit au fur et à mesure dans le fichier, sans être construit en mémoire.
    tape.windows1252_reader()
        .json()
        .with_options(options)
        .to_writer(&mut writer)
        .and_then(|()| writer.flush())
        .map_err(|e| format!("écriture de {output} impossible : {e}"))
}

/// Renvoie le texte à parser sans en tête, ou une erreur pour les formats non gérés.
fn gamestate_text(data: &[u8]) -> Result<&[u8], String> {
    if data.starts_with(ZIP_MAGIC) {
        return Err("sauvegarde compressée (zip) : pas encore gérée".into());
    }
    if data.starts_with(BINARY_HEADER) {
        return Err("sauvegarde binaire (ironman) : non gérée".into());
    }
    Ok(data.strip_prefix(TEXT_HEADER).unwrap_or(data))
}
