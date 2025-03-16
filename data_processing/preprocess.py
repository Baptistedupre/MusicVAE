import os
import pandas as pd
import numpy as np
import pretty_midi
import warnings
from joblib import Parallel, delayed


def get_genres(path):
    """
    Reads the genre labels and puts them into a pandas DataFrame.

    Parameters
    ----------
    path : str
        The path to the genre label file. The genre dataset can be found here:
        https://www.tagtraum.com/msd_genre_datasets.html under Genre Ground truth (CD1 zip file).

    Returns
    -------
    pandas.DataFrame
        A pandas DataFrame containing the genres and MIDI IDs.
    """
    ids = []
    genres = []
    with open(path) as f:
        line = f.readline()
        while line:
            if line[0] != "#":
                [x, y, *_] = line.strip().split("\t")
                ids.append(x)
                genres.append(y)
            line = f.readline()
    genre_df = pd.DataFrame(data={"Genre": genres, "TrackID": ids})
    return genre_df


def get_matched_midi(midi_folder, genre_df):
    """
    Loads MIDI file paths found in the given folder, puts this data into a pandas DataFrame,
    then matches each entry with a genre described in get_genres.

    Parameters
    ----------
    midi_folder : str
        The path to the MIDI files. The MIDI dataset can be found here:
        https://colinraffel.com/projects/lmd/ (LMD matched dataset in tar format).
    genre_df : pandas.DataFrame
        The genre label DataFrame generated by get_genres.

    Returns
    -------
    pandas.DataFrame
        A DataFrame of track ID and path to a MIDI file with that track ID.
    """
    # Get All MIDI Files
    track_ids, file_paths = [], []
    for dir_name, _, file_list in os.walk(midi_folder):
        track_id = dir_name.split("/")[-1]
        file_path_list = ["/".join([dir_name, file]) for file in file_list]
        for file_path in file_path_list:
            track_ids.append(track_id)
            file_paths.append(file_path)
    all_midi_df = pd.DataFrame({"TrackID": track_ids, "Path": file_paths})

    # Inner Join with Genre DataFrame
    df = pd.merge(all_midi_df, genre_df, on="TrackID", how="inner")
    return df.drop(["TrackID"], axis=1)


def normalize_features(features):
    """
    Normalizes the features to the range [-1, 1].

    Parameters
    ----------
    features : list of float
        The array of features.

    Returns
    -------
    list of float
        Normalized features.
    """
    tempo = (features[0] - 150) / 300
    num_sig_changes = (features[1] - 2) / 10
    resolution = (features[2] - 260) / 400
    time_sig_1 = (features[3] - 3) / 8
    time_sig_2 = (features[4] - 3) / 8
    return [tempo, num_sig_changes, resolution, time_sig_1, time_sig_2]


def get_features(path):
    """
    Extracts the features from a MIDI file given its path.

    Parameters
    ----------
    path : str
        The path to the MIDI file.

    Returns
    -------
    list of float
        The extracted features.
    """
    try:
        # Test for Corrupted MIDI Files
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            file = pretty_midi.PrettyMIDI(path)

            tempo = file.estimate_tempo()
            num_sig_changes = len(file.time_signature_changes)
            resolution = file.resolution
            ts_changes = file.time_signature_changes
            ts_1 = 4
            ts_2 = 4
            if len(ts_changes) > 0:
                ts_1 = ts_changes[0].numerator
                ts_2 = ts_changes[0].denominator
            return normalize_features([tempo, num_sig_changes, resolution, ts_1, ts_2])
    except:
        return None


def one_hot(labels, num_classes):
    """
    Encodes the labels using one-hot encoding.

    Parameters
    ----------
    labels : numpy.ndarray of int
        The genre labels to encode.
    num_classes : int
        The number of genres/classes.

    Returns
    -------
    numpy.ndarray of int
        The one-hot encoding of the labels.
    """
    return np.eye(num_classes)[labels].astype(int)


def process_row(row, genre_dict, num_classes):
    """
    Processes a single row to extract features and one-hot encode the genre.

    Parameters
    ----------
    row : pandas.Series
        A row from the DataFrame.
    genre_dict : dict
        A dictionary mapping genres to IDs.
    num_classes : int
        The number of genres/classes.

    Returns
    -------
    dict
        A dictionary with the processed data.
    """
    features = get_features(row["Path"])
    genre_id = genre_dict[row["Genre"]]
    one_hot_genre = one_hot(np.array([genre_id]), num_classes)[0]
    return {
        "Path": row["Path"],
        "Genre": row["Genre"],
        "OneHotGenre": one_hot_genre,
        "Features": features,
    }


def save_matching_csv(genre_path, midi_folder, output_path):
    """
    Creates a DataFrame with columns ["path", "genre", "one_hot_genre", "features"] by matching genres to MIDI files,
    and saves it as a JSON file.

    Parameters
    ----------
    genre_path : str
        The path to the genre label file.
    midi_folder : str
        The path to the MIDI files.
    output_path : str
        The path where the output CSV file will be saved.
    """
    genre_df = get_genres(genre_path)
    matched_df = get_matched_midi(midi_folder, genre_df)

    # One-hot encode genres
    genre_list = matched_df["Genre"].unique()
    genre_dict = {genre: idx for idx, genre in enumerate(genre_list)}
    num_classes = len(genre_list)

    # Process rows in parallel
    processed_data = Parallel(n_jobs=-1)(
        delayed(process_row)(row, genre_dict, num_classes)
        for _, row in matched_df.iterrows()
    )

    # Create new DataFrame from processed data
    processed_df = pd.DataFrame(processed_data)

    # Drop rows with None features
    processed_df = processed_df.dropna(subset=["Features"])

    # Save with better array representation
    processed_df.to_json(output_path, orient="records")


if __name__ == "__main__":
    save_matching_csv(
        "data/msd_tagtraum_cd1.cls",
        "data/lmd_matched/lmd_matched",
        "data/matching.json",
    )
